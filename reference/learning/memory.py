"""Private, revisioned semantic memory. Only explicit admin operations can write shared scopes."""
import argparse
import array
import contextlib
import datetime
import fcntl
import functools
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import re
import sqlite3
import struct
import time
import unicodedata

MODEL = Path(__file__).resolve().parent / "potion-base-8M"
DEFAULT_DB = Path.home() / ".local/state/codex-learning/memory.sqlite3"
KINDS = {"preference", "fact", "environment", "decision", "state", "blocker", "next_action", "lesson", "workflow", "project", "skill"}
# A provider key can be short, unlabeled, or embedded in a URL or filename.
HINDSIGHT_KEY = re.compile(r"hsk_[a-z0-9._~+/=-]+", re.I)
SECRET = re.compile(r"""(?ix)
    -----BEGIN\s+[A-Z\s]*PRIVATE\s+KEY
    |\b(?:bearer|basic)\s+[\w/+.-]{12,}
    |\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{18,}|github_pat_[\w]{12,}|AKIA[0-9A-Z]{16}|xox[baprs]-[\w-]{12,}|eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,})
    |(?:password|passwd|secret|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|credential)\s*(?:[=:\x22']+\s*|\s+is\s+)\S+
    |[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@
    |(?<![\w-])[\w+/=-]{48,}(?![\w-])
""" + "|" + HINDSIGHT_KEY.pattern)
STOP = set("""a about actually all am an and any are as at be been before being by can choose could current did do does environment fact facts for from get give go going had has have how i if in into is it its just know let like me memory most my of on one or our ours please prefer preference preferred project remember should so some something tell than that the their them then there they this to use used using want was we what when where which who will with would you your""".split())
KEY_RE = re.compile(r"[\w][\w. /:-]{0,119}\Z")
SCHEMA = """
CREATE TABLE IF NOT EXISTS banks (id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS facts (
 id INTEGER PRIMARY KEY, bank TEXT NOT NULL REFERENCES banks(id), key TEXT NOT NULL,
 value TEXT NOT NULL, kind TEXT NOT NULL, aliases TEXT NOT NULL, source TEXT NOT NULL,
 observed_at REAL NOT NULL, recorded_at REAL NOT NULL, confidence TEXT NOT NULL,
 vector BLOB NOT NULL, active INTEGER NOT NULL, UNIQUE(bank,key,source,value)
);
CREATE UNIQUE INDEX IF NOT EXISTS current_slot ON facts(bank,key) WHERE active=1;
CREATE INDEX IF NOT EXISTS current_bank ON facts(active,bank);
CREATE TABLE IF NOT EXISTS erased (bank TEXT NOT NULL, key_hash TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY(bank,key_hash));
CREATE VIRTUAL TABLE IF NOT EXISTS words USING fts5(body, tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS bands (bank TEXT NOT NULL, band INTEGER NOT NULL, fact INTEGER NOT NULL, PRIMARY KEY(bank,band,fact));
CREATE INDEX IF NOT EXISTS bands_by_fact ON bands(fact);
"""
PUBLIC = "id,bank,key,value,kind,aliases,source,observed_at,recorded_at,confidence,active"


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def identities(cwd):
    cli_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").resolve()
    # OAuth secrets are never used, copied or logged. Select only the account/owner identity.
    identity = "local-profile"
    auth = cli_home / "auth.json"
    if auth.is_file():
        data = json.loads(auth.read_bytes()).get("tokens") or {}
        identity = str(data.get("account_id", "")) + "|" + str(data.get("login_owner_id", ""))
    user = digest(f"{os.getuid()}|{cli_home}|{identity}")[:24]
    machine = Path("/etc/machine-id")
    machine = machine.read_text().strip() if machine.exists() else os.uname().nodename
    env = digest(f"{user}|{machine}")[:24]
    root = Path(cwd).resolve(strict=True)
    for path in (root, *root.parents):
        if (path / ".git").exists():
            root = path
            break
    return {"user": "user-" + user, "environment": "env-" + env,
            "project": "project-" + digest(f"{env}|{root}")[:24]}


def terms(text):
    return [w for w in re.findall(r"[^\W_]+", text.lower()) if len(w) > 1 and w not in STOP][:80]


@functools.lru_cache(maxsize=1)
def weights():
    vocab = {word: i for i, word in enumerate((MODEL / "vocab.txt").read_text().splitlines())}
    with (MODEL / "model.safetensors").open("rb") as f:
        table = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    start = 8 + struct.unpack_from("<Q", table)[0]
    spec = json.loads(table[8:start])["embeddings"]
    if spec != {"dtype": "F32", "shape": [len(vocab), 256], "data_offsets": [0, len(vocab)*1024]} or len(table) != start + len(vocab)*1024:
        raise ValueError("Invalid pinned embedding weights; reinstall the memory model")
    return vocab, table, start


def embedding(s):
    vocab, table, start = weights()
    # English BERT WordPiece, mean pooling, unit normalization. Limit pathological words.
    normalized = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c))
    ids = []
    for word in re.findall(r"[^\W_]+|[^\w\s]|_", normalized)[:256]:
        if len(word) > 100:
            continue
        pos, pieces = 0, []
        while pos < len(word):
            end = len(word)
            while end > pos:
                piece = ("" if pos == 0 else "##") + word[pos:end]
                if piece in vocab:
                    break
                end -= 1
            if end == pos:
                pieces = []
                break
            pieces.append(vocab[piece])
            pos = end
        ids.extend(pieces)
    rows = [struct.unpack_from("<256f", table, start + 1024*i) for i in ids]
    sums = list(map(sum, zip(*rows))) if rows else [0.0]*256
    norm = math.sqrt(sum(x*x for x in sums)) or 1
    return array.array("f", (x/norm for x in sums))


def band_keys(vector):
    # 32 independent sign buckets for approximate search in larger banks.
    return [i*256 + sum((vector[8*i+j] >= 0) << j for j in range(8)) for i in range(32)]


def stamp(value):
    if value is None:
        return time.time()
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("observed_at requires UTC offset")
            value = dt.timestamp()
    out = float(value)
    if not math.isfinite(out) or out <= 0:
        raise ValueError("invalid observed_at")
    return out


def safe_text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or SECRET.search(re.sub(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", "id", value)):
        raise ValueError("field empty, too long or potentially contains a credential")
    value = value.strip()
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("unexpected control or formatting character")
    return value


class Memory:
    def __init__(self, db_path, cwd, scope="project"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.db_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(fd).st_uid != os.getuid():
                raise ValueError("memory database belongs to a different user")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        self.scopes = identities(cwd)
        self.bank = self.scopes[scope]
        self.db = sqlite3.connect(self.db_path, timeout=4)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA secure_delete=ON")
        with self.db:
            self.db.executescript(SCHEMA)
            for b in self.scopes.values():
                self.db.execute("INSERT OR IGNORE INTO banks(id) VALUES (?)", (b,))
            assert self.db.execute("SELECT 1 FROM banks WHERE id=?", (self.bank,)).fetchone()

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def _write(self):
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            yield

    def _unindex(self, row_id):
        self.db.execute("DELETE FROM words WHERE rowid=?", (row_id,))
        self.db.execute("DELETE FROM bands WHERE fact=?", (row_id,))
        self.db.execute("UPDATE facts SET active=0 WHERE id=?", (row_id,))

    def retain(self, key, value, source, *, kind="fact", aliases=(), observed_at=None, confidence="verified"):
        key = safe_text(key, 120).lower()
        if not KEY_RE.fullmatch(key) or kind not in KINDS or confidence not in ("verified", "explicit", "reported"):
            raise ValueError("invalid fact key, kind, or confidence")
        value, source = safe_text(value, 512), safe_text(source, 200)
        if not isinstance(aliases, (tuple, list)) or len(aliases) > 8:
            raise ValueError("expected up to eight short recall phrases")
        aliases = list(dict.fromkeys(safe_text(a, 96) for a in aliases))
        when = stamp(observed_at)
        body = " ".join([key.replace("_"," "), value, *aliases])
        vec = embedding(" ".join(terms(body)) or body)
        with self._write():
            erased = self.db.execute("SELECT at FROM erased WHERE bank=? AND key_hash=?", (self.bank,digest(key))).fetchone()
            if erased and when <= erased[0]:
                return None
            seen = self.db.execute("SELECT id FROM facts WHERE bank=? AND key=? AND source=? AND value=?", (self.bank,key,source,value)).fetchone()
            if seen:
                return seen[0]
            current = self.db.execute("SELECT * FROM facts WHERE bank=? AND key=? AND active=1", (self.bank,key)).fetchone()
            if current and current["value"] == value:
                if when > current["observed_at"]:
                    self.db.execute("UPDATE facts SET observed_at=? WHERE id=?", (when,current["id"]))
                return current["id"]
            active = not current or (when,source) > (current["observed_at"],current["source"])
            if active and current:
                self._unindex(current["id"])
            row_id = self.db.execute(
                "INSERT INTO facts(bank,key,value,kind,aliases,source,observed_at,recorded_at,confidence,vector,active) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (self.bank,key,value,kind,json.dumps(aliases),source,when,time.time(),confidence,vec.tobytes(),int(active))
            ).lastrowid
            if active:
                self.db.execute("INSERT INTO words(rowid, body) VALUES (?,?)", (row_id,body))
                self.db.executemany("INSERT INTO bands VALUES (?,?,?)", ((self.bank,b,row_id) for b in band_keys(vec)))
            return row_id

    def _public(self, row):
        info = {k: row[k] for k in PUBLIC.split(",")}
        info["aliases"] = json.loads(info["aliases"])
        info["scope"] = next(k for k,v in self.scopes.items() if v == info["bank"])
        return info

    def all(self, history=False):
        return [self._public(r) for r in self.db.execute(
            "SELECT "+PUBLIC+" FROM facts WHERE bank=? AND (? OR active=1) ORDER BY key,observed_at DESC",
            (self.bank,int(history)))]

    def recall(self, query, limit=4):
        query = str(query)[:3000]
        tokens = set(terms(query))
        limit = min(max(0, int(limit)), 8)
        if not tokens or not limit:
            return []
        banks = list(self.scopes.values())
        recent = self.db.execute("SELECT id FROM facts WHERE active=1 AND bank IN (?,?,?) ORDER BY id DESC LIMIT 257", banks).fetchall()
        if not recent:
            return []
        qv = embedding(" ".join(terms(query)))
        if len(recent) <= 256:
            candidates = {r[0] for r in recent}
        else:
            bands = band_keys(qv)
            marks = ",".join("?" * len(bands))
            matches = self.db.execute("SELECT fact FROM bands WHERE bank IN (?,?,?) AND band IN ("+marks+") GROUP BY fact ORDER BY count(*) DESC,fact DESC LIMIT 256", [*banks,*bands])
            candidates = {r[0] for r in matches}
            lexical = " OR ".join('"'+t+'"' for t in sorted(tokens)[:30])
            candidates.update(r[0] for r in self.db.execute("SELECT words.rowid FROM words JOIN facts ON facts.id=words.rowid WHERE words MATCH ? AND bank IN (?,?,?) ORDER BY rank LIMIT 128", [lexical,*banks]))
        ranked = []
        if not candidates:
            return []
        marks = ",".join("?"*len(candidates))
        for row in self.db.execute("SELECT * FROM facts WHERE active=1 AND bank IN (?,?,?) AND id IN ("+marks+")", [*banks,*candidates]):
            record = self._public(row)
            exact = tokens.intersection(terms(" ".join([record["key"],record["value"],*record["aliases"]])))
            sim = math.sumprod(qv, memoryview(row["vector"]).cast("f"))
            score = sim + 0.22 * min(1.0, len(exact)/min(len(tokens),3))
            ranked.append((score,record["observed_at"],record["id"],bool(exact),record))
        ranked.sort(reverse=True)
        results = []
        for i,(score,_,_,lexical_match,record) in enumerate(ranked):
            clear_lead = i == 0 and (len(ranked) == 1 or score - ranked[1][0] >= .08)
            if score >= .42 or (lexical_match and score >= .34) or (clear_lead and score >= .27):
                results.append(record)
        return results[:limit]

    def reflect(self, query):
        """Collect bounded, source-attributed evidence for the existing main model to synthesize."""
        evidence = self.recall(query, limit=8)
        if evidence:
            # Expand one hop through the most relevant decision or state. No extra model calls.
            related = self.recall(evidence[0]["key"]+" "+evidence[0]["value"], limit=5)
            for item in related:
                if len(evidence) >= 8:
                    break
                if item["id"] not in {fact["id"] for fact in evidence}:
                    evidence.append(item)
        return {"operation":"reflect", "method":"synthesize_in_main_turn", "evidence":evidence}

    def delete(self, key):
        key = safe_text(key,120).lower()
        with self._write():
            self.db.execute("INSERT INTO words(words,rank) VALUES ('secure-delete',1)")
            rows = self.db.execute("SELECT id,observed_at FROM facts WHERE bank=? AND key=?", (self.bank,key)).fetchall()
            for row in rows:
                self._unindex(row["id"])
            self.db.execute("DELETE FROM facts WHERE bank=? AND key=?", (self.bank,key))
            self.db.execute("INSERT INTO erased VALUES (?,?,?) ON CONFLICT(bank,key_hash) DO UPDATE SET at=max(at,excluded.at)", (self.bank,digest(key), max(time.time(),max((r["observed_at"] for r in rows), default=0))))
            return len(rows)

    def purge(self, key):
        """Erase all revisions and scrub the learning queue for affected turns in this bank."""
        key = safe_text(key,120).lower()
        state = self.db_path.parent
        stats = {"fact_revisions":0, "scrubbed_turns":0, "skill_revisions":0}
        with (state / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            # Re-read after serialization with the reviewer.
            revisions = self.db.execute(
                "SELECT value,source FROM facts WHERE bank=? AND key=?", (self.bank,key)
            ).fetchall()
            values = [r["value"].casefold() for r in revisions if len(r["value"]) >= 4]
            origins = {tuple(r["source"].split("/")[:2]) for r in revisions}
            queue = state / "learning.db"
            if queue.is_file():
                db = sqlite3.connect(queue,timeout=10)
                db.row_factory = sqlite3.Row
                try:
                    db.execute("PRAGMA secure_delete=ON")
                    with db:
                        db.execute("BEGIN IMMEDIATE")
                        topic = key.removeprefix("skill/") if key.startswith("skill/") else None
                        if topic and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", topic):
                            for row in db.execute("SELECT source FROM lessons WHERE scope=? AND topic=?", (self.bank,topic)):
                                origins.add(tuple(row["source"].split("/")[:2]))
                            stats["skill_revisions"] = db.execute("DELETE FROM lessons WHERE scope=? AND topic=?", (self.bank,topic)).rowcount
                            path = state/"skills"/self.bank/topic/"SKILL.md"
                            if path.is_file():
                                if not path.resolve().is_relative_to((state/"skills").resolve()/self.bank):
                                    raise ValueError("skill file resolves beyond selected bank")
                                path.unlink()
                        jobs = db.execute("""SELECT j.* FROM jobs j JOIN origins o USING(session,turn)
                                             WHERE o.bank=?""", (self.bank,)).fetchall()
                        for job in jobs:
                            pair = (job["session"],job["turn"])
                            raw = job["result"] or "{}"
                            bundle = json.loads(raw)
                            review = bundle.get("review", bundle)
                            linked = pair in origins or any(str(r.get("key","")).lower() == key for r in review.get("memories",[]))
                            linked |= bool(topic and any(r.get("topic") == topic for r in review.get("lessons",[])))
                            if not linked:
                                hay = " ".join(job[k] or "" for k in ("prompt","final","result","error")).casefold()
                                linked = any(v in hay for v in values)
                            if not linked and values:
                                for row in db.execute("SELECT text FROM events WHERE session=? AND turn=?",pair):
                                    if any(v in row[0].casefold() for v in values):
                                        linked = True
                                        break
                            if not linked:
                                continue
                            # A source turn may combine many kinds of evidence. Remove its payload
                            # as a unit so a pending review cannot regenerate deleted material.
                            audit = json.dumps({"decision":review.get("decision"),"purged":True})
                            db.execute("""UPDATE jobs SET status=CASE WHEN status='done' THEN 'done' ELSE 'purged' END,
                                      result=?,prompt='',final='',error='' WHERE session=? AND turn=?""", (audit,*pair))
                            db.execute("DELETE FROM events WHERE session=? AND turn=?",pair)
                            db.execute("DELETE FROM candidates WHERE session=? AND turn=?",pair)
                            stats["scrubbed_turns"] += 1
                    checkpoint = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    if checkpoint[0]:
                        stats["warning"] = "WAL checkpoint busy. Rerun purge to truncate released pages."
                finally:
                    db.close()
            # Last so an interrupted purge retains the source references needed to retry.
            stats["fact_revisions"] = self.delete(key)
        return stats

    def rollback(self, key):
        key = safe_text(key,120).lower()
        r = self.db.execute("SELECT * FROM facts WHERE bank=? AND key=? AND active=0 ORDER BY observed_at DESC,recorded_at DESC LIMIT 1", (self.bank,key)).fetchone()
        if not r:
            raise ValueError("no prior revision in selected scope")
        return self.retain(key,r["value"],f"operator-rollback/{r['id']}/{time.time_ns()}",kind=r["kind"],aliases=json.loads(r["aliases"]),confidence=r["confidence"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--cwd", type=Path, default=Path.cwd())
    p.add_argument("--scope", choices=("project","user","environment"),default="project")
    sub = p.add_subparsers(dest="action",required=True)
    for name in ("list","export"):
        sub.add_parser(name).add_argument("--history",action="store_true")
    for name in ("recall","reflect"):
        sub.add_parser(name).add_argument("query")
    put = sub.add_parser("correct")
    put.add_argument("key"); put.add_argument("value"); put.add_argument("--alias",action="append", default=[])
    put.add_argument("--kind",choices=sorted(KINDS),default="fact")
    purge = sub.add_parser("purge",help="Erase every revision plus matching learning-queue turns in this bank. A skill/NAME key also erases that learned skill and its revisions.")
    purge.add_argument("key")
    for name in ("delete","rollback"):
        sub.add_parser(name).add_argument("key")
    args = p.parse_args()
    mem = Memory(args.db,args.cwd,args.scope)
    try:
        if args.action in ("list","export"):
            data = mem.all(args.history)
        elif args.action == "correct":
            data = mem.retain(args.key,args.value,f"operator/{time.time_ns()}",kind=args.kind,aliases=args.alias,confidence="explicit")
        elif args.action in ("recall","reflect"):
            data = getattr(mem,args.action)(args.query)
            if args.scope=="project" and (Path.home()/".config/codex-learning/hindsight.key").is_file() and not (args.db.parent/"paused").exists():
                import sys
                sys.path.insert(0,str(Path(__file__).resolve().parent))
                import hindsight_store
                deep=args.action=="reflect"
                remote=hindsight_store.retrieve(mem,args.query,deep=deep,on_demand=True)
                local=data["evidence"] if deep else data
                combined=list({f["id"]:f for f in [*remote["facts"],*local]}.values())[:8 if deep else 4]
                if deep:
                    data["evidence"]=combined
                    if remote["reflection"]:
                        data["method"]="hindsight_reflect"
                        data["synthesis"]=remote["reflection"]
                else: data=combined
                if remote["warning"]: print(remote["warning"],file=sys.stderr)
        else:
            data = getattr(mem,args.action)(args.key)
        print(json.dumps(data,ensure_ascii=False,indent=2))
    finally:
        mem.close()

if __name__ == "__main__":
    main()
