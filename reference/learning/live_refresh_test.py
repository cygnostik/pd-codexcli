"""Exercise updated skills and within-turn preflight on a single loaded Codex thread."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB))
from reviewer import _Rpc


def run():
    with tempfile.TemporaryDirectory(prefix="learning-loaded-") as tmp:
        home = Path(tmp) / "home"
        codex = home / ".codex"
        work = Path(tmp) / "project"
        codex.mkdir(parents=True, mode=0o700)
        work.mkdir()
        (codex/"auth.json").symlink_to(Path.home()/".codex/auth.json")
        env = dict(os.environ, HOME=str(home), CODEX_HOME=str(codex))
        subprocess.run([sys.executable,"-I",str(LIB/"install.py"),"install"],env=env,cwd=work,check=True)
        cmd = [shutil.which("codex") or "/root/.local/bin/codex", "app-server", "--stdio"]
        for feature in ("multi_agent", "apps", "plugins"):
            cmd.extend(["--disable",feature])
        with subprocess.Popen(cmd,cwd=work,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL) as proc:
            try:
                rpc = _Rpc(proc)
                rpc.call("initialize",{"clientInfo":{"name":"live_learning_test","version":"1"},
                                       "capabilities":{"experimentalApi":True}})
                rpc.send({"method":"initialized"})
                options = {"cwd":str(work),"model":"gpt-6-luna","modelProvider":"openai",
                           "allowProviderModelFallback":False,"approvalPolicy":"never",
                           "sandbox":"read-only","config":{"skills.include_instructions":False}}
                thread = rpc.call("thread/start",options)["thread"]["id"]
                print("App server PID",proc.pid,"thread",thread,flush=True)
                def turn(prompt):
                    rpc.deadline = time.monotonic()+90
                    tid = rpc.call("turn/start",{"threadId":thread,"input":[{"type":"text","text":prompt}],
                                                 "effort":"low"})["turn"]["id"]
                    final = ""
                    while True:
                        packet = rpc.read()
                        method,params = packet.get("method"),packet.get("params",{})
                        if method=="item/agentMessage/delta":
                            final += params.get("delta","")
                        elif method=="turn/completed" and params["turn"]["id"]==tid:
                            assert params["turn"]["status"]=="completed",params["turn"]["status"]
                            break
                    db = home/".local/state/codex-learning/learning.db"
                    with sqlite3.connect(db) as conn:
                        deadline = time.monotonic()+80
                        while time.monotonic() < deadline:
                            result = conn.execute("select status,error from jobs where session=? and turn=?",(thread,tid)).fetchone()
                            if result and result[0]=="done":
                                break
                            if result and result[1]:
                                raise RuntimeError(result[1])
                            time.sleep(.3)
                        else: raise TimeoutError("Review incomplete")
                        blocks = conn.execute("select n from counters where name='blocked'").fetchone()
                    print(tid,final[-500:],"preflight denials",blocks,flush=True)
                    return tid,final,blocks
                first = turn("Compatibility probe for this project's recurring toolchain check. In separate shell tool calls execute /usr/bin/ls --versoin verbatim then /usr/bin/ls --version. Verify the repair by checking the exit code.")
                skills = list((home/".local/state/codex-learning/skills").rglob("cli-option-corrections/SKILL.md"))
                assert len(skills)==1 and "/usr/bin/ls --version" in skills[0].read_text()
                second = turn("Run the following separate shell calls in order as an intentional pre-tool guard test: /usr/bin/sort --versoin then /usr/bin/sort --version then /usr/bin/sort --versoin again. Do attempt the third tool call and if a pre-tool guard denies it report that without retrying.")
                skill = skills[0].read_text()
                assert "/usr/bin/ls --version" in skill and "/usr/bin/sort --version" in skill
                assert second[2] and second[2][0]>0
                last = turn("For the recurring sort toolchain check, what did the local cli-option-corrections skill verify? Give the exact working command without running any tools.")
                path = next((codex/"sessions").rglob("*"+thread+".jsonl"))
                items = [json.loads(l) for l in path.read_text().splitlines()]
                start = next(i for i,m in enumerate(items) if m["type"]=="event_msg" and m["payload"].get("type")=="task_started" and m["payload"].get("turn_id")==last[0])
                parts = [c["text"] for m in items[start:] if m["type"]=="response_item" and m["payload"].get("role")=="developer" for c in m["payload"].get("content",[]) if c.get("type")=="input_text"]
                assert any("cli-option-corrections" in p and "/usr/bin/sort --version" in p for p in parts), "No updated skill delivered"
                assert "/usr/bin/sort --version" in last[1]
                print("PASS existing thread received updated skill; prevented within-turn retry before Stop",flush=True)
            finally:
                proc.kill()


if __name__=="__main__":
    run()
