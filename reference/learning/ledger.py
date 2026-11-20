"""Private, scoped materializations and evidence from the native Codex event stream."""
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import tempfile
import time

STATE = Path.home()/'.local/state/codex-learning'
CODEX = Path(os.environ.get('CODEX_HOME', Path.home()/'.codex')).resolve()
ERROR = re.compile(r'command not found|unknown (?:option|argument|flag)|unrecognized (?:option|argument)|invalid option|no such file|syntax error|traceback|permission denied|unexpected argument', re.I)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]

def connect():
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(STATE/'learning.db', timeout=3, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('pragma journal_mode=WAL')
    db.execute('pragma secure_delete=on')
    db.executescript("""
    create table if not exists jobs(session,turn,cwd,path,prompt,final,created real,
      status default 'open', attempts integer default 0, retry real default 0, error default '',
      result,primary key(session,turn));
    create table if not exists events(session,turn,id,kind,text,primary key(session,turn,id));
    create table if not exists attempts(at real);
    create index if not exists attempts_time on attempts(at);
    create table if not exists candidates(session,turn,scope,bad,ref,primary key(session,turn,scope,bad));
    create table if not exists guards(scope,bad,good,source,primary key(scope,bad));
    create table if not exists lessons(scope,topic,source,body,created real,active integer default 1,
      primary key(scope,topic,source));
    create table if not exists projects(bank primary key,cwd,checked real default 0);
    create table if not exists origins(session,turn,bank,primary key(session,turn));
    create table if not exists replacements(scope,topic,source,previous,primary key(scope,topic,source,previous));
    create table if not exists offsets(session primary key, pos integer);
    create table if not exists issues(kind primary key,detail,at real);
    create table if not exists counters(name primary key,n integer);
    """)
    return db

def atomic(path, data):
    path.parent.mkdir(mode=0o700,exist_ok=True,parents=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False,mode='w') as f:
            name = f.name
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name,path)
        parent_fd=os.open(path.parent,os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)

def clean(text, cap=1200):
    from memory import SECRET
    from reviewer import _SECRET_PATH, redact
    value=str(text)
    # UUIDs are normal evidence references, including two IDs joined by a slash.
    probe = re.sub(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", "id", value)
    if SECRET.search(probe) or _SECRET_PATH.search(value) or PRIVATE_PATH.search(value):
        return '[sensitive record withheld]'
    value=redact(value)
    value=re.sub(r'[A-Za-z0-9+/=_-]{64,}','[opaque value withheld]',value)
    value=re.sub(r'\x1b\[[0-9;]*[a-zA-Z]|[\x00-\x08\x0b-\x1f\x7f]',' ',value)
    return value if len(value)<=cap else value[:cap*2//3]+' … '+value[-cap//3:]

PRIVATE_PATH = re.compile(r"""(?ix)
    (?:^|[/\s"'=])(?:\.env(?:[.][\w-]+)*|\.netrc|id_(?:ed25519|rsa|ecdsa)(?:[.]pem)?|credentials[.]json|auth[.]json)(?=$|[/\s"';])
    | hindsight[.]key | /(?:run|var/run)/secrets/ | \.config/gcloud/ | \.aws/credentials | \.ssh/ | /etc/(?:g?shadow)
""")
DIAGNOSTIC = re.compile(r"""(?ix)^\s*(?:
    (?:(?:[\w./-]+):(?:\s*line\s+\d+:)?\s*){1,3}(?:cannot\b|.*?(?:command\s+not\s+found|no\s+such\s+file|invalid\s+option|unrecognized\s+option|permission\s+denied|syntax\s+error))
    |(?:fatal|error|exception|failed)\s*[:(]|[a-z_][\w.]*?(?:Error|Exception):|
    Traceback\s+\(most\s+recent|usage:.*?error:|.*?:\s*(?:unknown|unexpected|invalid|unrecognized)\s+(?:option|argument|flag)
)""")

def shell_event(command, exit_code, reply, *, status=None):
    """Project a command into evidence; ordinary stdout never enters the review queue."""
    from memory import HINDSIGHT_KEY
    if isinstance(command,list):
        command=command[-1] if len(command)>=3 and command[1] in ('-lc','-c') else shlex.join(command)
    command=str(command or '')
    failed=exit_code not in (None,0) or str(status).lower() in ('failed','error','declined','denied')
    # Inspect a bounded amount of command/output without copying arbitrary file bodies.
    if isinstance(reply,dict):
        reply=reply.get('aggregated_output',reply.get('output',reply.get('stderr','')))
    sample=str(reply or '')
    if HINDSIGHT_KEY.search(sample):
        return ('failure' if failed else 'action', '[sensitive record withheld]')
    sample=sample[:4096]+'\n'+sample[-4096:] if len(sample)>8192 else sample
    cleaned=clean(command,440)
    if cleaned.startswith('[sensitive') or PRIVATE_PATH.search(sample):
        return ('failure' if failed else 'action', '[sensitive record withheld]')
    display=clean(command.splitlines()[0] if command.splitlines() else '',300)
    if '\n' in command: display+=' [multiline command body omitted]'
    summary = f"{display} [exit={exit_code}]"
    try:
        args=shlex.split(command)
    except ValueError:
        args=[]
    binary=Path(args[0]).name if args else ''
    # Positive exit status is authoritative. For successful compound commands also
    # capture diagnostic evidence of an earlier failed constituent.
    compound='\n' in command or bool(re.search(r'[;&|]',command))
    diags=[line.strip()[:220] for line in sample.splitlines() if DIAGNOSTIC.search(line)]
    inner=bool(compound and diags and binary not in ('cat','grep','rg','sed','head','tail'))
    if failed or inner or exit_code is None:
        if diags: summary+=' '+' | '.join(dict.fromkeys(diags[:3]))
    if exit_code==0 and not inner and len(args)>=2:
        line=next((s.strip() for s in sample.splitlines() if s.strip()),'')
        if (args[1] in ('--version','-V') and re.fullmatch(r'[a-zA-Z][ .()a-zA-Z0-9_+-]{0,95}\d[.][0-9][.\w+-]*',line)
            or binary=='wc' and re.fullmatch(r'\d+(?:\s+[^\r\n]{1,120})?',line)):
            summary+=' '+line
    return ('failure' if failed or inner else 'action', clean(summary,850))

def scope(cwd):
    from memory import identities
    return identities(cwd)['project']

def simple(command):
    if len(command)>256 or not re.fullmatch(r'[a-zA-Z0-9/_.= \t-]+',command):
        return None
    words=command.split()
    if len(words)!=2 or not re.fullmatch(r'(?:/usr/bin/|/bin/)?(?:ls|cat|sort|wc|head|tail|python3|git|rg|grep)',words[0]):
        return None
    if not re.fullmatch(r'--[a-z-]{2,40}',words[1]):
        return None
    return ' '.join(words)

def code(response):
    if isinstance(response,dict):
        for k in ('exit_code','exitCode','code'):
            if type(response.get(k)) is int:
                return response[k]
    # Plain stdout and nested user-controlled text cannot attest to process status.
    return None

def observe(db, session,turn,cwd,command,response,ref,exit_code):
    key=simple(command)
    if not key: return None
    bank=scope(cwd)
    if exit_code and ERROR.search(str(response)):
        db.execute('insert or ignore into candidates values(?,?,?,?,?)',(session,turn,bank,key,ref))
    if exit_code!=0 or key.split()[1] not in ('--version','--help'):
        return None
    for row in db.execute('select bad,ref from candidates where session=? and turn=? and scope=?',(session,turn,bank)):
        old=row['bad'].split()
        new=key.split()
        if old[0]!=new[0] or old[1]==new[1] or difflib.SequenceMatcher(None,old[1],new[1]).ratio()<0.70:
            continue
        source=f"{session}/{turn}/{row['ref']},{ref}"
        changed=db.execute('insert or ignore into guards values(?,?,?,?)',(bank,row['bad'],key,source)).rowcount
        if changed: return f"Observed {row['bad']} fail and {key} succeed in this workspace."
    return None

def transcript(path,session):
    if not path: return None
    p=Path(path).resolve()
    if not p.is_relative_to(CODEX/'sessions') or not p.name.endswith(session+'.jsonl'): return None
    return p

def _tool_event(name, status, error, paths=()):
    from memory import HINDSIGHT_KEY
    failed = bool(error) or str(status).lower() in ('failed','error','declined','denied','cancelled','canceled')
    if isinstance(error,dict):
        error=error.get('message') or error.get('code') or 'tool reported error'
    if HINDSIGHT_KEY.search(str(error)) or any(HINDSIGHT_KEY.search(str(p)) for p in paths):
        return ('failure' if failed else 'action', '[sensitive record withheld]')
    # Errors may contain arbitrary content returned by a remote service. Keep
    # the first short diagnostic only and never successful response bodies.
    reason=str(error or '').splitlines()
    text=f"{name} [{status or ('failed' if failed else 'completed')}]"
    if reason: text+=' '+reason[0][:220]
    if paths: text+=' changed '+', '.join(str(v) for v in paths if v)[:400]
    return ('failure' if failed else 'action',clean(text,750))


def _output_error(value):
    if isinstance(value,str):
        if len(value)>16000:
            value=value[:8000]+'\n'+value[-8000:]
        if len(value)<=16000 and value.startswith('{'):
            try: return _output_error(json.loads(value))
            except ValueError: pass
        lines=value.splitlines()[:10]
        return next((l for l in lines if DIAGNOSTIC.search(l) or re.match(r'(?i)^\s*(?:tool call failed|failed to (?:run|apply|read)|patch verification failed|execution error)',l)),None)
    if isinstance(value,list):
        for item in value[:16]:
            if isinstance(item,dict) and item.get('type') in ('text','input_text'):
                error=_output_error(str(item.get('text',''))[:16000])
                if error: return error
    if isinstance(value,dict):
        if value.get('error'): return value['error']
        if value.get('isError') or value.get('is_error') or value.get('status') in ('failed','error'):
            return _output_error(value.get('content')) or 'tool reported failure'
    return None


def projection(db,job):
    """Merge turn-local evidence by native item identity, in native completion order."""
    sid,tid=job['session'],job['turn']
    queue={r['id']:dict(r) for r in db.execute('select id,kind,text from events where session=? and turn=? order by rowid',(sid,tid))}
    events={}
    native=set()
    def add(ref,kind,value,authoritative=False):
        if ref in native and not authoritative: return
        events[ref]=dict(id=ref,kind=kind,text=clean(value))
        if authoritative: native.add(ref)
    if job['prompt']: add('prompt','user',job['prompt'])
    p=transcript(job['path'],sid)
    end=None
    if p and p.is_file():
        row=db.execute('select pos from offsets where session=?',(sid,)).fetchone()
        with p.open('rb') as f:
            header=json.loads(f.readline())['payload']
            if header.get('thread_source')=='subagent' or isinstance(header.get('source'),dict):
                raise ValueError('Refusing non-user transcript')
            def scan(offset):
                f.seek(offset)
                live=seen=False
                end=None
                calls={}
                while raw:=f.readline():
                    a=json.loads(raw)
                    v=a.get('payload',{}); t=v.get('type'); channel=a['type']
                    if channel=='event_msg' and t=='task_started':
                        if live and v.get('turn_id')!=tid: break
                        live=v.get('turn_id')==tid
                        seen |= live
                    if not live: continue
                    end=f.tell()
                    if channel=='event_msg' and t=='item_completed':
                        it=v.get('item',{})
                        typ=it.get('type','')
                        ref=it.get('id') or 'native-'+str(end)
                        if typ=='UserMessage':
                            msg=' '.join(str(x.get('text','')) for x in it.get('content',[]) if isinstance(x,dict))
                            if msg and (not job['prompt'] or not msg.startswith(str(job['prompt'])[:200])):
                                add(ref,'user',msg,True)
                        elif typ=='CommandExecution':
                            kind,text=shell_event(it.get('command'),it.get('exit_code'),it.get('aggregated_output'),status=it.get('status'))
                            add(ref,kind,text,True)
                        elif typ in ('FileChange','McpToolCall','DynamicToolCall','PatchApply','WebSearch','CollabToolCall','Extension'):
                            changes=it.get('changes') or []
                            paths=list(changes)[:12] if isinstance(changes,dict) else [x.get('path') for x in changes[:12] if isinstance(x,dict)]
                            result=it.get('result')
                            error=it.get('error') or (result.get('error') if isinstance(result,dict) else None)
                            bad_status=str(it.get('status','')).lower() in ('failed','error','denied','declined','cancelled','canceled')
                            if isinstance(result,dict) and not error and (bad_status or result.get('isError')):
                                error=_output_error(result.get('content')) or 'tool reported failure'
                            name=it.get('tool') or it.get('name') or it.get('kind') or typ
                            kind,text=_tool_event(str(name)[:90],it.get('status'),error,paths)
                            add(ref,kind,text,True)
                    elif channel=='event_msg' and t=='error':
                        kind,text=_tool_event('Codex runtime','failed',v.get('message') or 'turn error')
                        add('error-'+str(end),kind,text,True)
                    elif channel=='response_item' and t in ('function_call','custom_tool_call'):
                        ref=v.get('call_id')
                        name=str(v.get('name','tool'))[:80]
                        args=str(v.get('arguments') or v.get('input') or '')
                        private=clean(args,80).startswith('[sensitive')
                        paths=re.findall(r'^\*\*\* (?:Add|Delete|Update) File: ([^\r\n]+)',args,re.M)[:12] if 'patch' in name else []
                        calls[ref]=(name,private,paths)
                    elif channel=='response_item' and t in ('function_call_output','custom_tool_call_output'):
                        ref=v.get('call_id') or 'tool-'+str(end)
                        if ref in native: continue
                        name,private,paths=calls.pop(ref,('tool',False,[]))
                        error=_output_error(v.get('output')) if not private else None
                        if name not in ('exec','wait','exec_command','write_stdin') or error:
                            kind,text=_tool_event(name,None,error,paths)
                            add(ref,kind,'[sensitive record withheld]' if private else text)
                    if t=='task_complete': break
                return seen,end
            start=row[0] if row else 0
            seen,end=scan(start)
            if not seen and start: seen,end=scan(0)
    # Persist final status before review; this also corrects provisional hook
    # evidence on retry without retaining successful stdout.
    for ref,e in events.items():
        if e['kind']=='failure' or (ref in native and ref in queue and queue[ref]!=e):
            db.execute("""INSERT INTO events VALUES (?,?,?,?,?)
                ON CONFLICT(session,turn,id) DO UPDATE SET kind=excluded.kind,text=excluded.text
                WHERE events.kind!=excluded.kind OR events.text!=excluded.text""",(sid,tid,ref,e['kind'],e['text']))
    for ref,e in queue.items():
        if ref not in events:
            add(ref,e['kind'],e['text'])
    if job['final']: add('answer','assistant',job['final'])
    return list(events.values()),end

def publish(db, bank, topic):
    # Read the committed revision set while holding the same lock as every other
    # publisher. A slow writer can never replace a newer materialization.
    if not re.fullmatch(r"project-[0-9a-f]{24}",bank) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*",topic):
        raise ValueError("invalid learned skill destination")
    with (STATE/"publish.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        _publish(db,bank,topic)

def _publish(db, bank, topic):
    path=STATE/'skills'/bank/topic/'SKILL.md'
    rows=list(db.execute('select body,source from lessons where scope=? and topic=? and active=1 order by created',(bank,topic)))
    if not rows:
        path.unlink(missing_ok=True)
        return
    des=json.loads(rows[-1]['body'])['applicability']
    body=[f'---\nname: {topic}\ndescription: {json.dumps(des,ensure_ascii=False)}\n---\n', '# '+topic+'\n']
    for r in rows:
        lesson=json.loads(r['body'])
        body.extend([lesson['applicability'],lesson['procedure'],f"Evidence {r['source']} ({lesson['verification']})."])
        if lesson.get('uncertainty'): body.append('Uncertainty: '+lesson['uncertainty'])
    atomic(path,'\n\n'.join(body)+'\n')

def lookup(db,cwd,query,limit=3):
    bank=scope(cwd)
    stop={'with','this','that','what','which','from','your','should','please','would','using','about','have','could','before','after','there','tool','when','command','show','again','want','need','does','will','make','then','read','only','file','help','work','answer','reply','exact','return','project','verified','check','next'}
    def terms(s): return {i for i in re.findall(r'[a-z0-9][a-z0-9_-]+',s.lower()) if i not in stop}
    wanted=terms(query)
    scored=[]
    for r in db.execute('select topic,body,source from lessons where active and scope=? order by created desc',(bank,)):
        b=json.loads(r['body']); overlap=wanted & terms(r['topic'].replace('-',' ')+' '+b['applicability']+' '+b['procedure'])
        if overlap: scored.append((len(overlap),{**b,'topic':r['topic'],'source':r['source']}))
    return [v for _,v in sorted(scored,key=lambda item:-item[0])[:limit]]
