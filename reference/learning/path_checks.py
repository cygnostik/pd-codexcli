"""Learn project-local input path corrections from completed native shell events."""
import difflib
import json
import re
import shlex
import stat
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ledger import clean, publish, scope

TOPIC = "input-path-corrections"
COMMANDS = {
    "cat": {"-n"}, "wc": {"-l", "-w", "-c"}, "head": set(), "tail": set(),
    "stat": set(), "sha256sum": set(), "md5sum": set(),
}
SENSITIVE = re.compile(r"(?i)passw(?:or)?d|credential|secret|token|(?:private|api|signing|client|ssh)[ _.-]?key|auth[_.-]|(?:\.pem|\.key|\.p12|\.pfx)$")
PATH_CHARS = re.compile(r"[A-Za-z0-9_./ -]{1,220}\Z")
SAFE_COMMAND = re.compile(r"""[A-Za-z0-9_./ '"-]{1,320}\Z""")
REF = re.compile(r"[a-zA-Z0-9_-]{1,90}\Z")
PROJECT_FILES = {".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".toml", ".yaml",
                 ".yml", ".py", ".js", ".ts", ".rs", ".go", ".c", ".cpp", ".h",
                 ".sh", ".sql", ".xml", ".ini", ".lock", ".log"}


def project_root(cwd):
    root = Path(cwd).resolve(strict=True)
    return next((p for p in (root, *root.parents) if (p / ".git").exists()), root)


def input_path(root, cwd, value):
    if not isinstance(value, str) or not PATH_CHARS.fullmatch(value):
        return None
    p = Path(value)
    if ".." in p.parts or str(p) == "." or value.startswith("-"):
        return None
    if not p.is_absolute():
        if not cwd or not Path(cwd).is_absolute():
            return None
        p = Path(cwd) / p
    if not p.is_relative_to(root):
        return None
    rel = p.relative_to(root)
    if not rel.parts or any(
        part.startswith(".") or SENSITIVE.search(part) or clean(part, 255) != part for part in rel.parts
    ):
        return None
    if p.suffix.lower() not in PROJECT_FILES and p.name not in {"README", "Makefile", "Dockerfile", "LICENSE"}:
        return None
    # Refuse symlinks and special files, even when their names are inside this project.
    current = root
    for part in rel.parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return rel.as_posix(), False
        except OSError:
            return None
        if stat.S_ISLNK(mode) or (current != p and not stat.S_ISDIR(mode)):
            return None
    return (rel.as_posix(), True) if stat.S_ISREG(mode) else None


def literal(command, root, cwd):
    """Keep exactly one literal file operand, with a small read-only flag vocabulary."""
    if not isinstance(command, str):
        return None
    # A literal absolute cd makes relative operands unambiguous in a native Bash
    # prehook even when the caller's custom workdir is not in the hook payload.
    match = re.fullmatch(r"""cd\s+(/[-A-Za-z0-9_./]+)\s+&&\s+(.+)""", command)
    if match:
        cwd, command = match.groups()
        if ".." in Path(cwd).parts:
            return None
    if not SAFE_COMMAND.fullmatch(command):
        return None
    try:
        args = shlex.split(command)
    except ValueError:
        return None
    if len(args) < 2 or len(args) > 5:
        return None
    program = Path(args[0]).name
    if program not in COMMANDS or args[0] not in {program, "/usr/bin/"+program, "/bin/"+program}:
        return None
    flags = args[1:-1]
    if flags and flags[-1] == "--":
        flags = flags[:-1]
    if not all(flag in COMMANDS[program] for flag in flags):
        return None
    path = input_path(root, cwd, args[-1])
    return (program, " ".join(flags), *path) if path else None


def local_cwd(value):
    if not isinstance(value, str):
        return None
    if value.startswith("/"):
        return value
    uri = urlsplit(value)
    if uri.scheme == "file" and not uri.netloc and not uri.query and not uri.fragment:
        return unquote(uri.path)
    return None


def native_commands(path, turn):
    if not path or not path.is_file():
        return []
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - 262144))
        raw = handle.read(262144)
    result = []
    for line in raw.splitlines():
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        payload = record.get("payload", {})
        if record.get("type") == "event_msg" and payload.get("turn_id") == turn and payload.get("type") == "item_completed":
            item = payload.get("item", {})
            if item.get("type") == "CommandExecution":
                result.append(item)
    return result[-32:]


def observation(item, root):
    argv = item.get("command")
    ref = item.get("id")
    if not isinstance(argv, list) or len(argv) != 3 or argv[1] not in ("-lc", "-c"):
        return None
    if not isinstance(ref, str) or not REF.fullmatch(ref):
        return None
    native_cwd = local_cwd(item.get("cwd"))
    if not native_cwd or not Path(native_cwd).is_relative_to(root):
        return None
    args = literal(argv[2], root, native_cwd)
    if not args or type(item.get("exit_code")) is not int:
        return None
    program, flags, rel, exists = args
    failed = item["exit_code"] != 0 and item.get("status") == "failed"
    if failed and not exists:
        sample = str(item.get("aggregated_output") or "")[:900]
        if "no such file or directory" not in sample.lower() or Path(rel).name not in sample:
            return None
    elif not (item["exit_code"] == 0 and exists and item.get("status") == "completed"):
        return None
    return program, flags, rel, failed, ref


def learn_pair(db, bank, prefix, old, new):
    program, flags, missing, _, old_ref = old
    correct, new_ref = new[2], new[4]
    # Only infer a suggested correction from adjacent, matching reads of similar
    # filenames in the same directory. Absence itself is checked again at use.
    if old[:2] != new[:2] or missing == correct or Path(missing).parent != Path(correct).parent:
        return False
    before, after = Path(missing).name, Path(correct).name
    if difflib.SequenceMatcher(None, before, after).ratio() < .79:
        return False
    evidence = prefix + old_ref + "," + new_ref
    guard = [program, flags, missing, correct]
    body = {"applicability": f"Using {program} to read {missing} in this project.",
            "procedure": f"The read of {missing} failed. The next {program} read of {correct} succeeded. "
                         f"Check that the intended file is {correct} and verify that the read exits successfully.",
            "verification": "verified", "uncertainty": "File names and contents can change.",
            "path_guard": guard}
    encoded = json.dumps(body)
    saved = db.execute("""insert or ignore into lessons(scope,topic,source,body,created)
        select ?,?,?,?,? where not exists
        (select 1 from lessons where scope=? and topic=? and body=? and active)""",
        (bank, TOPIC, evidence, encoded, time.time(), bank, TOPIC, encoded))
    return bool(saved.rowcount)


def check(db, hook, path, bank, *, learn=True):
    event = hook.get("hook_event_name")
    if event != "Stop" and hook.get("tool_name") != "Bash":
        return None
    args = hook.get("tool_input") or {}
    command = args.get("command", "") if isinstance(args, dict) else ""
    if event != "Stop" and (not isinstance(command, str) or not any(p in command for p in COMMANDS)):
        return None
    # CLI 0.170 sends the effective tool workdir in top-level cwd, including
    # when exec_command overrides the session cwd. Use the submitted project's
    # identity for in-project subdirectories, including workspaces outside Git.
    origin = db.execute("""select j.cwd,o.bank from jobs j join origins o using(session,turn)
        where j.session=? and j.turn=? and j.status!='purged'""",
        (hook["session_id"], hook["turn_id"])).fetchone()
    if not origin or scope(origin[0]) != origin[1]:
        return None
    root = project_root(origin[0])
    effective = Path(hook["cwd"]).resolve(strict=True)
    if not effective.is_relative_to(root) or (bank != origin[1] and bank != scope(effective)):
        return None
    nested = project_root(effective)
    if nested != root and (nested / ".git").exists():
        return None
    bank = origin[1]
    cwd = local_cwd(args.get("workdir", str(effective))) if isinstance(args, dict) else None
    if learn:
        previous = None
        changed = False
        for item in native_commands(path, hook["turn_id"]):
            current = observation(item, root)
            if previous and previous[3] and current and not current[3]:
                changed |= learn_pair(db, bank, hook["session_id"]+"/"+hook["turn_id"]+"/", previous, current)
            previous = current
        if changed:
            publish(db, bank, TOPIC)
    if event != "PreToolUse":
        return None
    pending = literal(command, root, cwd)
    if not pending or pending[3]:
        return None
    program, flags, missing, _ = pending
    rows = db.execute("""select json_extract(body,'$.path_guard[3]') from lessons
        where scope=? and topic=? and active=1 and json_extract(body,'$.path_guard[0]')=?
        and json_extract(body,'$.path_guard[1]')=? and json_extract(body,'$.path_guard[2]')=?
        order by created desc""", (bank, TOPIC, program, flags, missing))
    for (correct,) in rows:
        if input_path(root, root, correct) == (correct, True):
            return f"Verified path preflight: {missing} is still absent. A previous {program} read succeeded for {correct}. Check the intended input before retrying."
    return None
