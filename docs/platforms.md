# Platform guide

This repository contains a setup prompt and a Linux-oriented reference snapshot, not a finished cross-platform installer. No macOS, Windows, or WSL installation has been validated by this repository. Run `python3 tools/preflight.py` in the environment that will run Codex. The inventory reports a candidate hostname-based bank; it does not verify Hindsight rules or connections.

| Target | Starting point | Main adaptation |
| --- | --- | --- |
| Linux | Native user account and filesystem | Replace original `/root` and executable paths, verify Codex hooks, and configure a suitable user scheduler. |
| macOS | Native terminal and user account | Adapt Linux-specific process, socket, command and service assumptions; use a per-user launchd job if appropriate. |
| Windows | WSL 2 Linux distribution | Install and run Codex and the learning integration inside the same distribution; treat it as a separate Linux environment. |
| Native Windows | PowerShell and Windows-native Codex | Requires a substantive port; do not run the snapshot unchanged. |

## Common requirements and configuration

The inventory itself supports Python 3.8 or later. The learning snapshot imports `tomllib`, requiring Python 3.11 or newer unless adapted, plus a Python SQLite build with FTS5. Check Codex version, account and current hook interfaces, and verify the included embedding assets before enabling hooks. Existing settings must be merged and backed up. Hooks require explicit trust for their actual definitions; do not reuse another machine's trust hashes.

Codex user configuration is normally `~/.codex/config.toml` in the environment running Codex; `CODEX_HOME` may change it. On native Windows, `~` refers to the Windows user's home; in WSL it refers to the Linux user's home. Skills, hooks, credentials and state in these environments are separate. Use `~/.agents/skills` for user skills and verify discovery in a fresh session. The bundled server skills describe the original Linux server and require review for the new host.

If deliberately choosing unrestricted command execution for a machine, the following are **top-level** TOML keys, placed before the first section such as `[tui]`:

```toml
sandbox_mode = "danger-full-access"
approval_policy = "never"
```

This grants broad access to the user's files, credentials, and network and suppresses approval prompts; it is not required for this toolkit. Existing managed policies or launch options can override the defaults. Do not combine `sandbox_mode` with `default_permissions` in the same configuration. See [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) and [security guidance](https://learn.chatgpt.com/docs/security).

## Linux and WSL

The reference uses `fcntl`, Unix ownership and permissions, a machine identity, absolute executable paths, and a systemd user timer. Adapt to the actual user and executable locations. Check `systemctl --user` and the timer's status; merely installing a unit does not prove background retries run. On WSL, a stopped distribution cannot run its retry worker, and Windows and WSL may have different hostnames, credentials, and Codex homes. Resolve the bank in the environment where the integration runs and report it.

Some WSL distributions already run systemd. If it is unavailable, consult [Microsoft's WSL configuration guide](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) before changing `/etc/wsl.conf`; enabling it and restarting WSL affects the distribution. Verify the user service actually runs after restart. Keep the code and state in the Linux home and validate filesystem locking and permissions there.

## macOS

macOS supplies Unix APIs including `fcntl`, but that alone does not make this snapshot portable. Replace `/root`, `/usr/bin/python3`, GNU-specific command assumptions, Linux socket peer-credential checks in `refresh.py`, and `systemctl` use. Adapt the offline runtime separately for the machine architecture. A per-user `launchd` job can provide periodic retries, but its environment, user session lifecycle, and restart behavior must be tested. Use restrictive permissions for local state and secrets. Verify hook events and SQLite FTS5 on the actual Python interpreter.

## Native Windows

The Python snapshot imports `fcntl` and assumes Unix user IDs, ownership bits, process paths, and Unix sockets; it cannot run unchanged. A native port needs tested equivalents for file locking, private storage and ACLs, identity, executable invocation, socket authentication, hook command quoting, scheduling, and cleanup. Task Scheduler may provide retries after login, but implement and verify it for the selected account. Until that work is complete, report native Windows learning and memory as unavailable rather than silently claiming success. The prompt and documentation can still be read, and WSL offers the closest starting environment.

## Bank naming and migration

Use the target runtime's hostname plus `-cli` as the proposed Hindsight bank. Validate the exact name against the deployed service before activation; if it must be normalized, use a deterministic scheme and report the actual bank. Hostname changes, WSL hostnames, and similarly named machines can change or collide with bank names. Never migrate, merge, overwrite, or delete existing banks automatically. Local scope identity also includes environment and workspace details, so using the same bank does not by itself reproduce another machine's private local state.
