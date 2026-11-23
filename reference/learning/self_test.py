"""Exercise the queue, hooks and rollback in a disposable home, without network calls."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))

def run(root):
    os.environ['HOME']=str(root)
    os.environ['CODEX_HOME']=str(root/'.codex')
    import learn, ledger, reviewer
    from memory import Memory
    learn.launch=lambda: None
    cwd=root/'project'
    cwd.mkdir()
    sid=str(uuid.uuid4())
    p=root/'.codex/sessions'/('rollout-'+sid+'.jsonl')
    p.parent.mkdir(parents=True)
    with p.open('w') as f:
        print(json.dumps({'type':'session_meta','payload':{'id':sid,'model_provider':os.environ.get('LEARNING_TEST_PROVIDER','openai'),'thread_source':'user'}}),file=f)
    def native(t,v):
        with p.open('a') as f: print(json.dumps({'type':t,'payload':v}),file=f)
    def event(turn, ev, **fields):
        return learn.hook(dict(session_id=sid,turn_id=turn,cwd=str(cwd),transcript_path=str(p),hook_event_name=ev,**fields))
    def start(prompt):
        turn=str(uuid.uuid4())
        native('event_msg',{'type':'task_started','turn_id':turn})
        return turn,event(turn,'UserPromptSubmit',prompt=prompt)
    def finish(turn):
        native('event_msg',{'type':'task_complete','turn_id':turn})
        return event(turn,'Stop',last_assistant_message='OK')
    def command(turn,cmd):
        spec=dict(tool_name='Bash',tool_input={'command':cmd})
        assert event(turn,'PreToolUse',**spec).get('hookSpecificOutput',{}).get('permissionDecision')!='deny'
        r=subprocess.run(['/bin/bash','-c',cmd],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        ref='exec-'+str(uuid.uuid4())
        item=dict(type='CommandExecution',id=ref,command=['/bin/bash','-c',cmd],cwd=cwd.as_uri(),
                  exit_code=r.returncode,status='failed' if r.returncode else 'completed',aggregated_output=r.stdout)
        native('event_msg',dict(type='item_completed',turn_id=turn,item=item))
        event(turn,'PostToolUse',tool_use_id=ref,tool_response=r.stdout,**spec)
        return ref
    db=ledger.connect()
    calls=[]
    down=False
    def inference(data):
        if down: raise reviewer.ReviewError('synthetic transport outage')
        calls.append(json.loads(data)['events'])
        events=calls[-1]
        output=dict(decision='no_change',memories=[],lessons=[],failures=[])
        user=next((e['text'] for e in events if e['kind']=='user'),'')
        if 'cover stock' in user:
            output['memories']=[dict(key='cover-stock',value='Ivory' if 'ivory' in user else 'Ochre',kind='preference',aliases=['binder cover paper color'],evidence_ids=['prompt'])]
        if 'sorted invoice' in user:
            ids=[e['id'] for e in events if e['kind']=='action']
            output['lessons']=[dict(topic='invoice-manifest',applicability='Validate a sorted invoice manifest',procedure='Run sort -c invoice.txt and verify exit zero.',verification='verified',uncertainty='',evidence_ids=ids)]
            output['decision']='create_skill'
        return output
    reviewer._inference=inference
    t,_=start('Thanks.')
    finish(t)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda x:event(t,'Stop',last_assistant_message='OK'),range(12)))
        list(pool.map(lambda x:learn.drain(),range(6)))
    assert len(calls)==1 and db.execute("select count(*) from jobs where status='done'").fetchone()[0]==1
    assert not Memory(learn.DBFILE,cwd).all()
    (cwd/'invoice.txt').write_text('alpha\nbeta\n')
    t,_=start('Run the sorted invoice check.')
    cid=command(t,'sort -c invoice.txt')
    finish(t); learn.drain()
    assert ledger.lookup(db,cwd,'sorted invoice')[0]['topic']=='invoice-manifest'
    assert any(e['id']==cid for e in calls[-1])
    assert all(e['text']!='Thanks.' for e in calls[-1])
    t,_=start('Check the CLI version.')
    command(t,'/usr/bin/ls --versoin')
    command(t,'/usr/bin/ls --version')
    denial=event(t,'PreToolUse',tool_name='Bash',tool_input={'command':'/usr/bin/ls --versoin'})
    assert denial['hookSpecificOutput']['permissionDecision']=='deny'
    assert ledger.lookup(db,cwd,'ls versoin')[0]['topic']=='cli-option-corrections'
    finish(t); learn.drain()
    t,_=start('I prefer ivory cover stock.')
    finish(t)
    down=True; learn.drain()
    assert 'outage' in db.execute('select error from jobs where turn=?',(t,)).fetchone()[0]
    down=False; learn.drain(True)
    m=Memory(learn.DBFILE,cwd)
    assert m.recall('binder cover paper color')[0]['value']=='Ivory'
    assert not m.recall('soccer goalkeepers')
    t,_=start('I now prefer ochre cover stock.')
    finish(t); learn.drain()
    assert [r['value'] for r in m.all() if r['key']=='cover-stock']==['Ochre']
    # Recover a completion if the process disappeared before dispatching Stop.
    t,_=start('Hello.')
    db.execute('update jobs set created=created-60 where turn=?',(t,))
    native('event_msg',dict(type='task_complete',turn_id=t))
    learn.drain()
    assert db.execute('select status from jobs where turn=?',(t,)).fetchone()[0]=='done'
    assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    clean=m.purge('cover-stock')
    assert clean['fact_revisions']==2 and not m.recall('binder cover paper color')
    sample_key = 'hsk_' + 'test-1234'
    initial_facts = m.db.execute('select count(*) from facts').fetchone()[0]
    try:
        m.retain('test credential check', sample_key, 'self-test')
    except ValueError:
        pass
    else:
        raise AssertionError('direct retain accepted a provider key')
    assert m.db.execute('select count(*) from facts').fetchone()[0] == initial_facts
    assert reviewer.redact('prefix/' + sample_key + '/suffix') == reviewer.HIDDEN
    assert ledger.shell_event('probe',1,'error: ' + sample_key)[1] == '[sensitive record withheld]'
    assert ledger._tool_event('probe','failed','x'*218 + sample_key)[1] == '[sensitive record withheld]'
    sensitive_turn,_=start('The value is ' + sample_key)
    assert db.execute('select prompt from jobs where turn=?',(sensitive_turn,)).fetchone()[0]=='[sensitive record withheld]'
    finish(sensitive_turn)
    learn.drain()
    assert all(sample_key not in event['text'] for event in calls[-1])
    assert reviewer.review([dict(id='example',kind='user',text=sample_key)])['decision']=='no_change'
    assert calls[-1][0]['text']=='[sensitive record withheld]'
    # A large projected turn previously exhausted Qwen's fixed output budget.
    from unittest.mock import patch
    from cpu_review import LOCAL_MODEL, parse
    evidence = [
        dict(id='u',kind='user',text='I use tabs for indentation. Run the repeatable repository checks.'),
        dict(id='a',kind='action',text='git status --short [exit=0]'),
        dict(id='b',kind='action',text='git diff --check [exit=0]'),
        dict(id='w',kind='failure',text='[sensitive record withheld]'),
        dict(id='f',kind='failure',text='Artifact integrity check failed.'),
    ]
    evidence += [dict(id=f'action-{i}',kind='action',text='Observed synthetic action. '*12) for i in range(40)]
    with patch.object(reviewer, '_inference', side_effect=reviewer.QuotaPause('synthetic quota gate')):
        local = reviewer.review(evidence)
    assert local['reviewer_model'] == LOCAL_MODEL
    assert [item['key'] for item in local['memories']] == ['indentation']
    assert [item['evidence_ids'] for item in local['lessons']] == [['a','b']]
    assert [item['evidence_id'] for item in local['failures']] == ['f']
    for quote in ('My preferred badge color for the Northwind project is seafoam.',
                  'Correction: my preferred Northwind badge color is now copper.'):
        # Qwen selected the correct sentence but proposed out-of-range word indices.
        data = dict(events=[dict(id='u',kind='user',text=quote)],existing_memory_keys=[])
        selected = dict(facts=[dict(event_id='u',kind='preference',quote=quote,subject='')],workflows=[])
        assert [item['key'] for item in parse(data,selected)['memories']] == ['northwind-badge-color']
    m.close()
    print('PASS duplicate Stop, parallel workers, uneventful turn, delta isolation, verified workflow, first correction, same-turn denial, outage/retry, immediate recall, supersession, missing Stop recovery, scoped purge, credential rejection')
if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='codex-learning-self-test-') as tmp:
        run(Path(tmp))
