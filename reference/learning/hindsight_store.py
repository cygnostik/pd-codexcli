"""Authenticated Hindsight Cloud adapter. Network access requires a verified activation."""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import threading
import time
from urllib import error, parse, request
import uuid

from memory import PUBLIC, safe_text, terms

DEFAULT = 'https://api.hindsight.vectorize.io'
BANK = 'codexcli'
ROOT = '/v1/default/banks/' + BANK
APP = 'codex-learning-v1'
CAPS = {'write':48, 'recall':144, 'reflect':4}
TABLES = """
CREATE TABLE IF NOT EXISTS hs_accounts(owner TEXT PRIMARY KEY, endpoint TEXT NOT NULL, token_hash TEXT NOT NULL, ready REAL NOT NULL);
CREATE TABLE IF NOT EXISTS hs_smoke(owner TEXT, endpoint TEXT, token_hash TEXT, nonce TEXT NOT NULL, PRIMARY KEY(owner,endpoint,token_hash));
CREATE TABLE IF NOT EXISTS hs_slots(bank TEXT,key TEXT,desired INTEGER,confirmed INTEGER,flight INTEGER,op TEXT,
  next_try REAL NOT NULL DEFAULT 0, touched REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(bank,key));
CREATE TABLE IF NOT EXISTS hs_calls(kind TEXT, at REAL);
CREATE INDEX IF NOT EXISTS hs_calls_at ON hs_calls(at);
CREATE TABLE IF NOT EXISTS hs_issues(owner TEXT, kind TEXT, message TEXT, retry REAL, PRIMARY KEY(owner,kind));
"""
TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS hs_new AFTER INSERT ON facts
WHEN NEW.active=1 AND NEW.bank LIKE 'project-%'
BEGIN
 INSERT INTO hs_slots(bank,key,desired) VALUES(NEW.bank,NEW.key,NEW.id)
 ON CONFLICT(bank,key) DO UPDATE SET desired=NEW.id,next_try=0;
END;
CREATE TRIGGER IF NOT EXISTS hs_erase AFTER DELETE ON facts
WHEN OLD.bank LIKE 'project-%' AND NOT EXISTS(SELECT 1 FROM facts WHERE bank=OLD.bank AND key=OLD.key AND active=1)
BEGIN UPDATE hs_slots SET desired=NULL,next_try=0 WHERE bank=OLD.bank AND key=OLD.key; END;
"""

class CloudError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CloudError('Hindsight redirected the authenticated request; verify the configured HTTPS origin')

def _private_file(path, limit, *, credential=False):
    try:
        fd=os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if credential: raise CloudError('Hindsight key file is missing') from None
        return None
    except OSError:
        raise CloudError('Cannot open Hindsight configuration securely') from None
    with os.fdopen(fd,'rb') as fp:
        mode=os.fstat(fd)
        if (not stat.S_ISREG(mode.st_mode) or mode.st_uid!=os.getuid() or
                mode.st_mode & (0o077 if credential else 0o022)):
            raise CloudError('Hindsight files must belong to this user; the key needs mode 0600 or 0400')
        data=fp.read(limit+1)
        if len(data)>limit: raise CloudError('Hindsight configuration exceeds size limit')
        return data

def _config():
    folder=Path.home()/'.config/codex-learning'
    raw=_private_file(folder/'hindsight.json',4096)
    try:
        obj=json.loads(raw) if raw else {}
        endpoint=obj.get('base_url',DEFAULT).rstrip('/')
        parts=parse.urlsplit(endpoint)
        _ = parts.port  # Reject malformed port specifications before using the credential.
        if (parts.scheme!='https' or not parts.hostname or parts.username or parts.password or
            parts.path or parts.query or parts.fragment or not re.fullmatch(r'[a-zA-Z0-9.:[\]-]+',parts.netloc)):
            raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise CloudError('Invalid Hindsight HTTPS origin configuration') from None
    secret=_private_file(folder/'hindsight.key',4096,credential=True).strip()
    if not (8<=len(secret)<=4096 and re.fullmatch(rb'[!-~]+',secret)):
        raise CloudError('Hindsight key file is empty or has invalid formatting')
    return endpoint,secret.decode('ascii'),hashlib.sha256(secret).hexdigest()

@contextlib.contextmanager
def _timeout(seconds):
    # urllib socket timeouts alone do not bound DNS or a slowly trickling body.
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)[0]:
        yield
        return
    def expired(*_):
        raise TimeoutError()
    prev=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,seconds)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,prev)

def _http(conf,method,path,data=None,timeout=3):
    payload=None if data is None else json.dumps(data,allow_nan=False,separators=(',',':')).encode()
    req=request.Request(conf[0]+path,method=method,data=payload,headers={
        'Authorization':'Bearer '+conf[1],'Content-Type':'application/json','Accept':'application/json',
        'User-Agent':'codex-learning/1'})
    opener=request.build_opener(request.ProxyHandler({}),NoRedirect())
    try:
        with _timeout(timeout),opener.open(req,timeout=timeout) as resp:
            body=resp.read(524289)
        if len(body)>524288: raise CloudError('Hindsight response exceeded size limit')
        parsed=json.loads(body) if body else {}
        if not isinstance(parsed,dict): raise ValueError()
        return parsed
    except error.HTTPError as exc:
        exc.close()
        raise CloudError('Hindsight returned HTTP '+str(exc.code),exc.code) from None
    except (OSError,error.URLError,TimeoutError):
        raise CloudError('Hindsight request unavailable or timed out') from None
    except (ValueError,UnicodeError):
        raise CloudError('Malformed Hindsight API response') from None

def _exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hs_accounts'").fetchone()

def install(mem):
    """Enable future-change capture; deliberately performs no backfill."""
    mem.db.executescript(TABLES+TRIGGERS)

def _credentials(mem):
    if not _exists(mem.db): return None
    row=mem.db.execute('SELECT * FROM hs_accounts WHERE owner=?',(mem.scopes['user'],)).fetchone()
    if not row: return None
    c=_config()
    if row['endpoint']!=c[0] or row['token_hash']!=c[2]:
        raise CloudError('Hindsight credential or origin changed; verify activation again')
    return c

def _attempt(db,kind):
    now=time.time()
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM hs_calls WHERE at<?',(now-86400,))
        used=db.execute('SELECT count(*) FROM hs_calls WHERE kind=?',(kind,)).fetchone()[0]
        if used>=CAPS[kind]: raise CloudError('Hindsight '+kind+' rolling daily request cap reached')
        db.execute('INSERT INTO hs_calls VALUES (?,?)',(kind,now))

def _save(db,sql,args=()):
    with db: db.execute(sql,args)

def _document(bank,key):
    return 'cl1-'+hashlib.sha256((bank+'\0'+key).encode()).hexdigest()

def _revision(row):
    return hashlib.sha256(json.dumps([row['id'],row['bank'],row['key'],row['value'],row['source']],separators=(',',':')).encode()).hexdigest()[:32]

def _tags(bank): return [APP,bank]

def _item(row):
    safe_text(row['key'],120)
    safe_text(row['value'],512)
    stamp=datetime.datetime.fromtimestamp(row['observed_at'],datetime.timezone.utc).isoformat()
    return {'document_id':_document(row['bank'],row['key']), 'content':row['key']+'. '+row['value'],
            'timestamp':stamp, 'context':'Distilled Codex project '+row['kind'], 'tags':_tags(row['bank']),
            'observation_scopes':'combined','update_mode':'replace',
            'metadata':{'origin':APP,'scope':row['bank'],'local_id':str(row['id']),'revision':_revision(row),
                        'source':hashlib.sha256(row['source'].encode()).hexdigest()[:32],'kind':row['kind'],
                        'confidence':row['confidence']}}

def _belongs(hit,row):
    if not isinstance(hit,dict): return False
    data=hit.get('metadata') or {}
    return (isinstance(data,dict) and isinstance(hit.get('tags'),list)
            and set(hit['tags'])==set(_tags(row['bank'])) and hit.get('document_id')==_document(row['bank'],row['key'])
            and data.get('origin')==APP and data.get('scope')==row['bank']
            and data.get('local_id')==str(row['id']) and data.get('revision')==_revision(row))

def _doc(conf,bank,key):
    try: obj=_http(conf,'GET',ROOT+'/documents/'+_document(bank,key))
    except CloudError as exc:
        if exc.status==404:return None
        raise
    # Guard every delete/readiness decision using this exact document, not an empty search.
    if obj.get('id')!=_document(bank,key) or obj.get('bank_id')!=BANK or set(obj.get('tags') or [])!=set(_tags(bank)):
        raise CloudError('Hindsight document ownership mismatch')
    meta=obj.get('document_metadata') or {}
    if meta.get('origin')!=APP or meta.get('scope')!=bank:
        raise CloudError('Hindsight document metadata ownership mismatch')
    return obj

def _delete(conf,bank,key):
    if _doc(conf,bank,key) is not None:
        _http(conf,'DELETE',ROOT+'/documents/'+_document(bank,key))
    if _doc(conf,bank,key) is not None: raise CloudError('Hindsight document deletion is awaiting confirmation')

def _operation(conf,op):
    try: obj=_http(conf,'GET',ROOT+'/operations/'+op)
    except CloudError as exc:
        if exc.status==404:return 'not_found'
        raise
    if obj.get('operation_id')!=op: raise CloudError('Unexpected Hindsight operation identity')
    status=obj.get('status')
    if status not in ('pending','processing','completed','failed','cancelled','not_found'):
        raise CloudError('Unknown Hindsight operation status')
    return status

def _submit(conf,row,op):
    reply=_http(conf,'POST',ROOT+'/memories',{'items':[_item(row)],'async':True,'operation_id':op},5)
    if not reply.get('success') or reply.get('bank_id')!=BANK or op not in [reply.get('operation_id'),*(reply.get('operation_ids') or [])]:
        raise CloudError('Missing expected Hindsight async acknowledgement')

def _search(conf,bank,keywords):
    return _http(conf,'POST',ROOT+'/memories/recall',{'query':keywords,'tags':_tags(bank),'tags_match':'exact',
         'types':['world','experience'],'budget':'low','max_tokens':420,'include':{'entities':None}},2.3)

def _issue(mem,kind,exc,delay=60):
    _save(mem.db,'INSERT OR REPLACE INTO hs_issues VALUES(?,?,?,?)',(mem.scopes['user'],kind,str(exc)[:150],time.time()+delay))

def _clear(mem,kind):
    _save(mem.db,'DELETE FROM hs_issues WHERE owner=? AND kind=?',(mem.scopes['user'],kind))

@contextlib.contextmanager
def _lock(mem,blocking=False):
    with (mem.db_path.parent/'hindsight-worker.lock').open('a') as fp:
        try: fcntl.flock(fp,fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        yield True

def activate(mem, *, replacement=None):
    # Schema alone never enqueues data or authorizes network access.
    mem.db.executescript(TABLES)
    owner=mem.scopes['user']
    current=_config()
    conf=current
    if replacement is not None:
        if not re.fullmatch(r'[!-~]{8,4096}',replacement): raise CloudError('Invalid Hindsight key format')
        conf=(current[0],replacement,hashlib.sha256(replacement.encode('ascii')).hexdigest())
    prove_with_current=False
    with _lock(mem) as acquired:
        if not acquired:raise CloudError('Hindsight worker busy; try again shortly')
        row=mem.db.execute('SELECT * FROM hs_accounts WHERE owner=?',(owner,)).fetchone()
        if row and row['endpoint']==conf[0] and row['token_hash']==conf[2]:return {'active':True,'already_verified':True}
        # Pin one authority per data store. Switching origins would strand old documents
        # and accidentally replicate private outbox entries to a different service.
        if row and row['endpoint']!=conf[0]:raise CloudError('Existing activation belongs to another endpoint; separate explicit migration required')
        if row and row['token_hash']!=conf[2]:
            # Never leak a live outbox to a new tenant merely because its bank has
            # the same label. Verify a previously stored, unguessable scoped document.
            old=mem.db.execute('''SELECT f.* FROM hs_slots s JOIN facts f ON s.confirmed=f.id
                  WHERE s.bank=? AND s.desired=s.confirmed AND f.active=1 LIMIT 1''',(mem.bank,)).fetchone()
            if old is None:
                if replacement is None or current[2]!=row['token_hash']:
                    raise CloudError('Changed Hindsight key; activate from a project with a previously confirmed document or replace the key while the enrolled key is still active')
                prove_with_current=True
            else:
                proof=_doc(conf,mem.bank,old['key'])
                if proof is None or (proof.get('document_metadata') or {}).get('revision')!=_revision(old):
                    raise CloudError('Changed Hindsight key did not verify continuity with the enrolled tenant')
        try:
            try: profile=_http(conf,'GET',ROOT+'/config')
            except CloudError as exc:
                if exc.status!=404 or row:raise
                _http(conf,'PUT',ROOT,{})
                profile=_http(conf,'GET',ROOT+'/config')
            if profile.get('bank_id')!=BANK:raise CloudError('Hindsight bank identity could not be verified')
            args=(owner,conf[0],conf[2])
            _save(mem.db,'INSERT OR IGNORE INTO hs_smoke VALUES(?,?,?,?)',(*args,uuid.uuid4().hex))
            nonce=mem.db.execute('SELECT nonce FROM hs_smoke WHERE owner=? AND endpoint=? AND token_hash=?',args).fetchone()[0]
            bank='project-smoke-'+nonce
            test={'id':0,'bank':bank,'key':'synthetic marker '+nonce[:8], 'value':'The artificial test lighthouse lamp color is periwinkle.',
                  'observed_at':1700000000,'source':'activation/'+nonce,'kind':'fact','confidence':'verified'}
            op=str(uuid.uuid5(uuid.NAMESPACE_URL,APP+nonce))
            state=_operation(conf,op)
            if state=='not_found':
                _attempt(mem.db,'write');_submit(conf,test,op)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                state=_operation(conf,op)
                if state in ('completed','cancelled','failed'):break
                time.sleep(.5)
            if state in ('failed','cancelled'):
                _delete(conf,bank,test['key'])
                _save(mem.db,'DELETE FROM hs_smoke WHERE owner=? AND endpoint=? AND token_hash=?',args)
                raise CloudError('Hindsight synthetic ingestion failed; cleanup confirmed')
            if state!='completed':
                raise CloudError('Synthetic Hindsight ingestion pending; activation will resume using the same operation')
            try:
                ready=False
                for _ in range(3):
                    _attempt(mem.db,'recall')
                    hits=_search(conf,bank,'artificial lighthouse lamp color periwinkle').get('results',[])
                    if any(_belongs(hit,test) and 'periwinkle' in str(hit.get('text','')).lower() for hit in hits):
                        ready=True
                        break
                    time.sleep(.45)
                if not ready:raise CloudError('Strict scoped recall did not return the synthetic fact and revision')
                if prove_with_current:
                    # The original authority must see the candidate's unique canary
                    # before any queued project records can move to the new key.
                    proof=_doc(current,bank,test['key'])
                    if not proof or (proof.get('document_metadata') or {}).get('revision')!=_revision(test):
                        raise CloudError('Replacement key points to a different bank')
            finally:
                _delete(conf,bank,test['key'])
                _save(mem.db,'DELETE FROM hs_smoke WHERE owner=? AND endpoint=? AND token_hash=?',args)
            install(mem)
            if replacement is not None:
                from ledger import atomic
                atomic(Path.home()/'.config/codex-learning/hindsight.key',replacement)
            _save(mem.db,'INSERT OR REPLACE INTO hs_accounts VALUES(?,?,?,?)',(*args,row['ready'] if row else time.time()))
            _clear(mem,'activation')
            return {'active':True,'bank':BANK,'async_retain':'completed','scoped_recall':'verified','synthetic_document_deleted':True}
        except CloudError as exc:
            _issue(mem,'activation',exc)
            raise

def _flush_one(mem,conf,r,ready):
    db=mem.db
    keys=(r['bank'],r['key'])
    row=db.execute('SELECT * FROM facts WHERE id=? AND bank=? AND key=? AND active=1',(r['desired'],*keys)).fetchone()
    if row and row['observed_at']<ready:
        # Never promote material predating this authority's activation.
        _save(db,'DELETE FROM hs_slots WHERE bank=? AND key=? AND desired=? AND confirmed IS NULL AND op IS NULL',(*keys,r['desired']))
        return
    op=r['op']
    if op:
        state=_operation(conf,op)
        if state in ('pending','processing'):
            _save(db,'UPDATE hs_slots SET next_try=? WHERE bank=? AND key=?',(time.time()+3,*keys))
            return
        if state=='not_found' and row and r['flight']==r['desired']:
            _attempt(db,'write');_submit(conf,row,op)
            _save(db,'UPDATE hs_slots SET next_try=? WHERE bank=? AND key=?',(time.time()+2,*keys))
            return
        if state=='not_found' and time.time()-r['touched']<60:
            _save(db,'UPDATE hs_slots SET next_try=? WHERE bank=? AND key=?',(time.time()+5,*keys))
            return
        if state=='completed' and row and r['flight']==r['desired']:
            doc=_doc(conf,*keys)
            if not doc or (doc.get('document_metadata') or {}).get('revision')!=_revision(row) or int(doc.get('memory_unit_count') or 0)<1:
                raise CloudError('Hindsight operation completed but the latest document revision has no verified indexed facts')
        if state in ('failed','cancelled'):
            _save(db,'UPDATE hs_slots SET flight=NULL,op=NULL WHERE bank=? AND key=?',keys)
            raise CloudError('Hindsight ingestion failed; current local revision remains queued')
        _save(db,'UPDATE hs_slots SET confirmed=flight,flight=NULL,op=NULL,error=\'\',next_try=0,attempts=0 WHERE bank=? AND key=?',keys)
        return
    if row is None:
        _attempt(db,'write');_delete(conf,*keys)
        _save(db,'DELETE FROM hs_slots WHERE bank=? AND key=? AND desired IS NULL',keys)
        return
    if r['confirmed']==r['desired']:return
    op=str(uuid.uuid4())
    _save(db,'UPDATE hs_slots SET op=?,flight=?,touched=? WHERE bank=? AND key=?',(op,row['id'],time.time(),*keys))
    _attempt(db,'write')
    _submit(conf,row,op)
    _save(db,'UPDATE hs_slots SET next_try=? WHERE bank=? AND key=?',(time.time()+2,*keys))

def flush(mem,limit=3):
    conf=_credentials(mem)
    if not conf:return {'active':False,'processed':0}
    if mem.bank!=mem.scopes['project']:return {'active':True,'processed':0}
    ready=mem.db.execute('SELECT ready FROM hs_accounts WHERE owner=?',(mem.scopes['user'],)).fetchone()[0]
    count=0
    with _lock(mem) as acquired:
        if not acquired:return {'active':True,'processed':0,'busy':True}
        rows=mem.db.execute("""SELECT * FROM hs_slots WHERE bank=? AND (desired IS NOT confirmed OR desired IS NULL OR op IS NOT NULL)
                    AND next_try<=? ORDER BY next_try,rowid LIMIT ?""",(mem.bank,time.time(),min(8,max(0,limit)))).fetchall()
        for r in rows:
            try:_flush_one(mem,conf,r,ready)
            except CloudError as exc:
                delay=min(3600,10*2**min(8,r['attempts']))
                _save(mem.db,'UPDATE hs_slots SET error=?,attempts=attempts+1,next_try=? WHERE bank=? AND key=?',
                      (str(exc)[:150],time.time()+delay,r['bank'],r['key']))
                _issue(mem,'write',exc,delay)
                break
            else: count+=1
        if count and not mem.db.execute("SELECT 1 FROM hs_slots WHERE bank=? AND error!=''",(mem.bank,)).fetchone():
            _clear(mem,'write')
    return {'active':True,'processed':count}

def _keywords(mem,query):
    # Only terms already present in documents this authority has retained can leave
    # the machine. Never submit the user's raw prompt, commands, paths or identifiers.
    from ledger import clean
    if not isinstance(query,str) or len(query)>10000 or clean(query,len(query))!=query:return ''
    rows=mem.db.execute("""SELECT f.key,f.value FROM hs_slots s JOIN facts f ON f.id=s.confirmed
            WHERE s.bank=? AND f.active=1 AND f.id=s.desired ORDER BY f.observed_at DESC LIMIT 512""",(mem.bank,)).fetchall()
    if not rows:return ''
    known=set()
    for r in rows:known.update(terms(r['key']+' '+r['value']))
    picked=list(dict.fromkeys(t for t in terms(query) if t in known and re.fullmatch(r'[a-z]{3,24}',t)))[:8]
    if not picked:
        hits=mem.recall(query,limit=1)
        if hits and hits[0]['bank']==mem.bank:
            picked=[t for t in terms(hits[0]['key']) if t in known and re.fullmatch(r'[a-z]{3,24}',t)][:5]
    return ' '.join(picked)

def _valid_records(mem,hits):
    unique={}
    for hit in hits[:40]:
        if not isinstance(hit,dict) or not isinstance(hit.get('metadata'),dict):return [],False
        ref=hit['metadata'].get('local_id','')
        if not isinstance(ref,str) or not re.fullmatch(r'[1-9]\d{0,17}',ref):return [],False
        row=mem.db.execute("""SELECT f.* FROM facts f JOIN hs_slots s ON s.confirmed=f.id AND s.desired=f.id
             AND s.bank=f.bank AND s.key=f.key WHERE f.active=1 AND f.id=? AND f.bank=?""",(int(ref),mem.bank)).fetchone()
        if not row or not _belongs(hit,row):return [],False
        unique[row['id']]=mem._public(row)
    return list(unique.values())[:4],len(hits)<=40

def retrieve(mem,query,deep=False,*,on_demand=False):
    answer={'facts':[],'reflection':'','warning':''}
    if not _exists(mem.db):return answer
    kind='reflect' if deep else 'recall'
    diagnostic_kind='reflect-on-demand' if deep and on_demand else kind
    try:
        conf=_credentials(mem)
        if not conf or mem.bank!=mem.scopes['project']:return answer
        issue=mem.db.execute('SELECT * FROM hs_issues WHERE owner=? AND kind=?',(mem.scopes['user'],diagnostic_kind)).fetchone()
        if issue and issue['retry']>time.time():answer['warning']=issue['message'];return answer
        keywords=_keywords(mem,query)
        if not keywords:return answer
        _attempt(mem.db,kind)
        if deep:
            resp=_http(conf,'POST',ROOT+'/reflect',{'query':'Synthesize prior decisions and experience concerning '+keywords,
                'tags':_tags(mem.bank),'tags_match':'exact','budget':'high' if on_demand else 'low','max_tokens':450 if on_demand else 320,'include':{'facts':{}},
                'exclude_mental_models':True,'fact_types':['world','experience'],'apply_all_directives':False},30 if on_demand else 4.2)
            evidence=resp.get('based_on') or {}
            records,ok=_valid_records(mem,evidence.get('memories') or [])
            if ok and records and not evidence.get('directives') and not evidence.get('mental_models'):
                from ledger import clean
                body=resp.get('text') or ''
                answer['reflection']=clean(body,1000)
                answer['facts']=records
        else:
            resp=_search(conf,mem.bank,keywords)
            for hit in (resp.get('results') or [])[:16]:
                records,ok=_valid_records(mem,[hit])
                if ok and records and records[0]['id'] not in {r['id'] for r in answer['facts']}:
                    answer['facts'].extend(records)
                if len(answer['facts'])>=4:break
        _clear(mem,diagnostic_kind)
    except (CloudError,OSError,sqlite3.Error,TypeError,KeyError,ValueError,AttributeError) as exc:
        msg=str(exc) if isinstance(exc,CloudError) else 'Hindsight response validation or local state unavailable'
        answer['warning']=msg
        try:_issue(mem,diagnostic_kind,CloudError(msg))
        except sqlite3.Error:pass
    return answer

def status(mem):
    out={'active':False,'bank':BANK,'daily_request_caps':CAPS,'pending':0,'issues':[]}
    if not _exists(mem.db):return out
    try:out['active']=_credentials(mem) is not None
    except CloudError as exc:out['issues'].append(str(exc))
    out['issues'] += [r[0] for r in mem.db.execute('SELECT message FROM hs_issues WHERE owner=?',(mem.scopes['user'],))]
    out['pending']=mem.db.execute("SELECT count(*) FROM hs_slots WHERE bank=? AND (confirmed IS NOT desired OR op IS NOT NULL OR desired IS NULL)",(mem.bank,)).fetchone()[0]
    out['attempts_24h']=dict(mem.db.execute('SELECT kind,count(*) FROM hs_calls WHERE at>? GROUP BY kind',(time.time()-86400,)))
    return out
