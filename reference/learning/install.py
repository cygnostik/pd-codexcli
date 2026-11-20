"""Install, inspect, and remove the four Codex user hooks with exact native trust."""
import ast
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent
CODEX = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
BIN = shutil.which("codex") or "/root/.local/bin/codex"
COMMAND = "/usr/bin/python3 -I " + shlex.quote(str(ROOT / "learn.py")) + " hook"
EVENTS = {"UserPromptSubmit": "userPromptSubmit", "PreToolUse": "preToolUse",
          "PostToolUse": "postToolUse", "Stop": "stop"}
START = "# BEGIN codex-learning exact hook trust\n"
END = "# END codex-learning exact hook trust\n"


def rpc(method, params):
    args = [BIN, "app-server", "--stdio"]
    messages = [{"id": 1, "method": "initialize", "params": {
        "clientInfo": {"name": "learning_installer", "version": "1.0"},
        "capabilities": {"experimentalApi": True}}},
        {"method": "initialized"}, {"id": 2, "method": method, "params": params}]
    import select
    import time
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, bufsize=0) as p:
        try:
            p.stdin.write(b"".join((json.dumps(x) + "\n").encode() for x in messages))
            until = time.monotonic() + 12
            buf = b""
            while time.monotonic() < until:
                if not select.select([p.stdout], [], [], max(0, until - time.monotonic()))[0]:
                    break
                block = os.read(p.stdout.fileno(), 65536)
                if not block:
                    break
                buf += block
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    obj = json.loads(line)
                    if obj.get("id") == 2:
                        if "error" in obj:
                            raise RuntimeError(obj["error"])
                        return obj["result"]
            raise RuntimeError(f"No app-server reply to {method}")
        finally:
            p.kill()


def installed(cwd):
    result = rpc("hooks/list", {"cwds": [str(cwd)]})
    entry = result["data"][0]
    if entry["errors"]:
        raise RuntimeError("Codex hook errors: " + str(entry["errors"]))
    return [h for h in entry["hooks"] if h.get("command") == COMMAND and
            Path(h["sourcePath"]).resolve() == (CODEX / "hooks.json").resolve()]


def atomic(path, data):
    if data is None:
        path.unlink(missing_ok=True)
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            os.replace(f.name, path)
        finally:
            Path(f.name).unlink(missing_ok=True)


def group():
    return {"hooks": [{"type": "command", "command": COMMAND, "timeout": 8}]}


def verify(rows, trust=False):
    if sorted(x["eventName"] for x in rows) != sorted(EVENTS.values()):
        raise RuntimeError("Missing or duplicate learning hooks")
    if any(h["handlerType"] != "command" or h["async"] or h["matcher"] is not None
           or h["timeoutSec"] != 8 or h["command"] != COMMAND for h in rows):
        raise RuntimeError("Unexpected learning hook definition")
    if trust and any(h["trustStatus"] != "trusted" or not h["enabled"] for h in rows):
        raise RuntimeError("Codex did not trust or enable all four definitions")


def configure(install):
    if install:
        for name in ("learn", "ledger", "reviewer", "memory"):
            path = ROOT / (name + ".py")
            ast.parse(path.read_text(), filename=str(path))
    CODEX.mkdir(parents=True, exist_ok=True, mode=0o700)
    hp, cp = CODEX / "hooks.json", CODEX / "config.toml"
    state = Path.home() / ".local/state/codex-learning"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "hook-install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = {p: p.read_bytes() if p.exists() else None for p in (hp, cp)}
        data = json.loads(before[hp] or b'{"hooks":{}}')
        config = (before[cp] or b"").decode()
        if START in config or END in config:
            if config.count(START) != 1 or config.count(END) != 1:
                raise RuntimeError("Ambiguous learning trust markers in config.toml")
            start, end = config.index(START), config.index(END) + len(END)
            config = config[:start] + config[end:]
        source = data.setdefault("hooks", {})
        for name in EVENTS:
            original = source.get(name, [])
            owned = [group()]
            if name in {"PreToolUse", "PostToolUse"}:
                owned.append(dict(group(), matcher="Bash"))
            groups = []
            found = False
            for existing in original:
                if existing in owned:
                    if found:
                        raise RuntimeError("Duplicate learning hook needs inspection")
                    found = True
                    if install:
                        groups.append(group())
                else:
                    if any(h.get("command") == COMMAND for h in existing.get("hooks", [])):
                        raise RuntimeError("An edited learning hook needs inspection")
                    groups.append(existing)
            if install and not found:
                groups.append(group())
            if groups:
                source[name] = groups
            else:
                source.pop(name, None)
        try:
            hookdata = json.dumps(data, indent=2).encode() + b"\n" if source or len(data) > 1 else None
            if hookdata != before[hp]:
                atomic(hp, hookdata)
            if install:
                rows = installed(Path.cwd())
                verify(rows)
                config += ("" if config.endswith("\n") or not config else "\n") + START
                for h in rows:
                    config += "[hooks.state." + json.dumps(h["key"]) + "]\n"
                    config += "trusted_hash = " + json.dumps(h["currentHash"]) + "\n"
                config += END
            tomllib.loads(config)
            if config.encode() != (before[cp] or b""):
                if cp.exists() and cp.read_bytes() != before[cp]:
                    raise RuntimeError("config.toml changed concurrently")
                atomic(cp, config.encode() or None)
            if install:
                verify(installed(Path.cwd()), trust=True)
        except Exception:
            atomic(hp, before[hp])
            if (cp.read_bytes() if cp.exists() else None) == (config.encode() or None):
                atomic(cp, before[cp])
            raise


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode in {"install", "uninstall"}:
        configure(mode == "install")
        sock = CODEX / "app-server-control/app-server-control.sock"
        if sock.is_socket():
            subprocess.run([sys.executable, "-I", str(ROOT / "refresh.py"), str(sock), mode], check=True)
    elif mode != "status":
        sys.exit("Usage: install.py [install|status|uninstall]")
    print(json.dumps([{k: h[k] for k in ("eventName", "trustStatus", "enabled")}
                      for h in installed(Path.cwd())]))
