"""Run controlled native CLI acceptance tests in a disposable profile and workspace.

Uses the existing ChatGPT account for bounded main and reviewer turns. Run explicitly.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

PROGRAM = Path(__file__).resolve().parent
CODEX = shutil.which("codex") or "/root/.local/bin/codex"


def main():
    with tempfile.TemporaryDirectory(prefix="learning-native-") as tmp:
        p = Path(tmp)
        home, cwd = p / "home", p / "project"
        codex_home = home / ".codex"
        codex_home.mkdir(parents=True, mode=0o700)
        cwd.mkdir()
        (cwd/"manifest.txt").write_text("amber\nindigo\n")
        (codex_home / "auth.json").symlink_to(Path.home() / ".codex/auth.json")
        env = dict(os.environ, HOME=str(home), CODEX_HOME=str(codex_home))
        env.pop("CODEX_THREAD_ID", None)
        env.pop("CODEX_SESSION_ID", None)
        state = home / ".local/state/codex-learning"
        def run(argv, timeout=90):
            v = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=cwd, env=env, timeout=timeout)
            if v.returncode:
                raise RuntimeError(f"{Path(argv[0]).name} exit={v.returncode}: " +
                                   v.stderr.decode(errors="replace")[-500:])
            return v.stdout.decode()
        def query(file, statement, args=()):
            path = state / file
            with sqlite3.connect("file:"+str(path)+"?mode=ro", uri=True) as db:
                db.row_factory = sqlite3.Row
                return [dict(r) for r in db.execute(statement, args)]
        def turn(prompt, resume=None):
            args = [CODEX,"exec","--skip-git-repo-check","--json","-m","gpt-6-luna",
                    "-c",'model_reasoning_effort="low"', "--disable", "multi_agent", "--disable", "apps", "--disable", "plugins", "-c", "skills.include_instructions=false"]
            if resume:
                args.extend(["resume",resume])
            out = run([*args,prompt])
            msgs = [json.loads(l) for l in out.splitlines() if l]
            sid = next(m["thread_id"] for m in msgs if m["type"] == "thread.started")
            assert msgs[-1]["type"] == "turn.completed", msgs[-1]
            final = [m["item"]["text"] for m in msgs if m.get("type")=="item.completed"
                     and m["item"]["type"]=="agent_message"][-1]
            commands = [m["item"] for m in msgs if m.get("type")=="item.completed"
                        and m["item"]["type"]=="command_execution"]
            path = next((codex_home/"sessions").rglob("*"+sid+".jsonl"))
            items = [json.loads(l) for l in path.read_text().splitlines()]
            start = max(i for i,m in enumerate(items)
                        if m["type"]=="event_msg" and m["payload"].get("type")=="task_started")
            turnid = items[start]["payload"]["turn_id"]
            contexts = [t["text"] for m in items[start:]
                        if m["type"]=="response_item" and m["payload"].get("role")=="developer"
                        for t in m["payload"].get("content",[]) if t.get("type")=="input_text"]
            print("native turn",sid,turnid,final[:190],"commands",
                  [(v["command"],v["exit_code"]) for v in commands],flush=True)
            return sid,turnid,final,contexts,commands
        def completed(turn):
            deadline = time.monotonic()+110
            while time.monotonic() < deadline:
                jobs = query("learning.db","select status,result,error,attempts from jobs where session=? and turn=?",turn[:2])
                if jobs and jobs[0]["status"]=="done":
                    print("review",jobs[0]['status'],jobs[0]['attempts'],str(jobs[0]['result'])[:290],flush=True)
                    return json.loads(jobs[0]['result'])
                if jobs and jobs[0]["error"]:
                    print("review diagnostic",jobs[0]["error"],flush=True)
                    raise RuntimeError(jobs[0]["error"])
                time.sleep(.3)
            raise TimeoutError(str(jobs))
        def facts():
            return query("memory.sqlite3","select key,value,active from facts")
        def lessons():
            return query("learning.db","select topic,body,source from lessons where active=1")
        print("native hook inventory",run([sys.executable,"-I",str(PROGRAM/"install.py"),"install"]),flush=True)
        ordinary = turn("Reply with only the word Hello.")
        result = completed(ordinary)
        assert not facts() and not lessons()
        print("PASS ordinary stop, no changes",flush=True)
        workflow = turn("Every Northwind release requires this manifest validation in this project. Verify the existing manifest.txt by running sort -c manifest.txt and then wc -l manifest.txt in separate shell calls. A successful release check has a sorted file and exactly two lines. Run and verify the workflow now.")
        completed(workflow)
        assert lessons(), "No reusable skill from workflow"
        print("PASS demonstrated reusable workflow saved",flush=True)
        bad = turn("For this controlled command failure test run /usr/bin/ls --versoin verbatim first, then /usr/bin/ls --version in a separate shell call to verify the repair. Report the outcomes.")
        completed(bad)
        rows = query("learning.db","select bad,good from guards")
        assert any(r["bad"]=="/usr/bin/ls --versoin" and r["good"]=="/usr/bin/ls --version" for r in rows),rows
        again = turn("This is a pre-tool hook acceptance test. Call the shell tool with /usr/bin/ls --versoin verbatim once. If denied, report the reason without trying again.",bad[0])
        assert not any("--versoin" in c["command"] and c.get("exit_code") is not None for c in again[4]),again[4]
        assert "--version" in again[2] or any("--version" in t and len(t)<3000 for t in again[3])
        print("PASS repeat bad action prevented, active lesson received",flush=True)
        completed(again)
        remember = turn("My preferred badge color for the Northwind project is seafoam. Please remember this project preference. Reply only OK; use no tools.")
        completed(remember)
        print("stored",facts(),flush=True)
        fresh = turn("What is my preferred Northwind badge color? Answer with just the color. Use no tools.")
        assert remember[0]!=fresh[0] and "seafoam" in fresh[2].lower()
        assert any("seafoam" in s.lower() and len(s)<4000 for s in fresh[3])
        completed(fresh)
        print("PASS fresh process and distinct thread received preference",flush=True)
        unrelated = turn("What is eleven plus eleven? Reply only with a number. Use no tools.")
        assert not any("seafoam" in s.lower() for s in unrelated[3])
        completed(unrelated)
        print("PASS unrelated request received no badge preference",flush=True)
        changed = turn("Correction: my preferred Northwind badge color is now copper. This replaces my previous project preference. Reply only OK; use no tools.")
        completed(changed)
        latest = turn("What is my preferred Northwind badge color now? Return only the color. Use no tools.")
        assert "copper" in latest[2].lower()
        assert not any("seafoam" in s.lower() for s in latest[3])
        completed(latest)
        active = [r for r in facts() if r["active"]]
        assert not any("seafoam" in r["value"].lower() for r in active),active
        print("PASS changed preference superseded, fresh recall",flush=True)
        jobs = query("learning.db","select session,turn,status,attempts from jobs")
        all_turns = [ordinary,workflow,bad,again,remember,fresh,unrelated,changed,latest]
        assert {(r["session"],r["turn"]) for r in jobs}=={r[:2] for r in all_turns}
        assert len(query("learning.db","select * from attempts")) == len(jobs),jobs
        print("PASS exactly one review per completed turn; no reviewer recursion",flush=True)


if __name__ == "__main__":
    main()
