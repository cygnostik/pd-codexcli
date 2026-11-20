# Operations and verification

## Before setup

Run `python3 tools/preflight.py` (or `py tools/preflight.py` in native Windows). It inspects executable and path presence, Python modules, platform and hostname. Its output may identify your machine and account paths; review before sharing. It does not read or print credentials or verify network access. Preserve and back up existing configuration and state before making changes. Do not put credentials, histories, databases, logs or private records in this repository.

The custom source snapshot includes the local embedding files but omits the offline reviewer executable and model. `reference/learning/self_test.py` exercises that fallback and can fail when they are absent; this does not prove all other components failed. Do not treat a partial run or historical results in `reference/learning/OPERATIONS.md` as an acceptance test for a new installation. Any live tests can consume account usage and must use isolated workspaces and synthetic data.

## Acceptance checklist

1. Confirm `codex` and the intended user, runtime, Codex home, Python, FTS5 and hostname. Confirm the proposed `<hostname>-cli` bank with the actual Hindsight service before activation.
2. Inspect merged hooks in the running Codex version. Confirm the four expected definitions are enabled and trusted and existing hooks remain intact. Start a fresh session and confirm skills discovery.
3. With temporary test data, verify local scoped write, recall, correction, restart persistence and isolation between unrelated workspaces. Check that historical records are treated as evidence, not instructions or authorization.
4. Verify a completed turn is queued and reviewed, the scheduler retries pending work, duplicate events do not cause duplicate processing, and failure is visible. Confirm the configured reviewer and budget actually exist on the account. If offline fallback is missing, record that limitation.
5. If authorized and connected, use a uniquely identified synthetic remote record to check retain, recall and deletion; verify cleanup. Check `codex-learning hindsight status` and the reported bank. Local memory must remain usable when remote sync is unavailable.
6. Record installed paths, versions, scheduler, bank, test outcomes and limitations without secrets. Verify pause, recovery and non-destructive uninstall procedures before relying on them.

## Routine commands after installation

Run in the workspace whose scoped records you intend to inspect: `codex-learning status`, `codex-learning failures`, `codex-learning skills "task"`, `codex-learning memory list`, and `codex-learning hindsight status`. `codex-learning pause` and `resume` control new learning. The exact implementation may be adapted on another platform; verify its help first. Use the reference operations guide for correction, deletion, sync and uninstall details, and check that an uninstall leaves existing data as intended.

Never assume local deletion has removed remote copies. For cloud erasure, use the installed integration's documented purge and synchronization process, then verify the remote result. Preserve local provenance and backups according to the user's preferences.
