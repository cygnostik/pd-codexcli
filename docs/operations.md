# Operations and verification

## Before setup

Run `python3 tools/preflight.py` (or `py tools/preflight.py` in native Windows). It inspects executable and path presence, Python modules, platform and hostname. Its output may identify your machine and account paths; review before sharing. It does not read or print credentials or verify network access. Preserve and back up existing configuration and state before making changes. Do not put credentials, histories, databases, logs or private records in this repository.

The custom source snapshot includes the local embedding files but omits the offline reviewer executable and model. `reference/learning/self_test.py` exercises that fallback and can fail when they are absent; this does not prove all other components failed. Do not treat a partial run or historical results in `reference/learning/OPERATIONS.md` as an acceptance test for a new installation. Any live tests can consume account usage and must use isolated workspaces and synthetic data.

## Skills

Install whole skill directories under a user skill path discovered by the target Codex version, typically `~/.agents/skills`. Start a fresh session and verify discovery. The original server's management skills were installed under `~/.codex/skills`. Review host-specific paths and tracker references before installing those skills elsewhere.

| Skill | Use |
| --- | --- |
| [codex-learned-procedures](../reference/skills/codex-learned-procedures/SKILL.md) | Look up scoped historical procedures and check their provenance and applicability. |
| [manage-server-performance](../reference/skills/manage-server-performance/SKILL.md) | Inspect CPU scaling, disk health, QEMU/KVM, passt, and locale. Includes an operations reference and rollback guidance. |
| [ubuntu-package-maintenance](../reference/skills/ubuntu-package-maintenance/SKILL.md) | Check Ubuntu Pro and ESM, review unattended upgrades, and verify requested APT maintenance. |
| [manage-server-network](../reference/skills/manage-server-network/SKILL.md) | Inspect or change host addresses, persistent network configuration, and service bindings. |
| [manage-nginx](../reference/skills/manage-nginx/SKILL.md), [manage-certbot](../reference/skills/manage-certbot/SKILL.md), [manage-ufw](../reference/skills/manage-ufw/SKILL.md) | Manage web routing, certificates and renewal, and host firewall rules. |
| [manage-hermes](../reference/skills/manage-hermes/SKILL.md) | Operate the Hermes service and its configuration trackers. |

The generated procedures under the learning state directory are scoped to the original environment. The bundled Ubuntu skill is a portable reference for the workflows seen there. For the optional upstream `router` skill, see [router controls](router.md#routing-policy).

## Acceptance checklist

1. Confirm `codex` and the intended user, runtime, Codex home, Python, FTS5 and hostname. Confirm the proposed `<hostname>-cli` bank with the actual Hindsight service before activation.
2. Inspect merged hooks in the running Codex version. Confirm the four expected definitions are enabled and trusted and existing hooks remain intact. Start a fresh session and confirm skills discovery.
3. With temporary test data, verify local scoped write, recall, correction, restart persistence and isolation between unrelated workspaces. Check that historical records are treated as evidence, not instructions or authorization.
4. Verify a completed turn is queued and reviewed, the scheduler retries pending work, duplicate events do not cause duplicate processing, and failure is visible. Confirm the configured reviewer and budget actually exist on the account. If offline fallback is missing, record that limitation.
5. If authorized and connected, use a uniquely identified synthetic remote record to check retain, recall and deletion; verify cleanup. Check `codex-learning hindsight status` and the reported bank. Local memory must remain usable when remote sync is unavailable.
6. Record installed paths, versions, scheduler, bank, test outcomes and limitations without secrets. Verify pause, recovery and non-destructive uninstall procedures before relying on them.
7. If routing is enabled, verify a fresh routed thread and a direct OpenAI thread, the actual replies, and queue completion for each provider. Check [router verification](router.md#verify-the-route-and-learning) for the difference between a selected route and a completed routed reply.

With the optional local reviewer installed beside the reference files or installed learning code, run the isolated self-test once per transcript provider:

```sh
LEARNING_TEST_PROVIDER=openai python3 -I reference/learning/self_test.py
LEARNING_TEST_PROVIDER=router python3 -I reference/learning/self_test.py
```

Both synthetic provider runs passed on the reference Linux host with its installed offline reviewer. They exercise queue behavior without live model or Hindsight requests.

## Routine commands after installation

Run in the workspace whose scoped records you intend to inspect: `codex-learning status`, `codex-learning failures`, `codex-learning skills "task"`, `codex-learning memory list`, and `codex-learning hindsight status`. `codex-learning pause` and `resume` control new learning. The exact implementation may be adapted on another platform; verify its help first. Use the reference operations guide for correction, deletion, sync and uninstall details, and check that an uninstall leaves existing data as intended.

Never assume local deletion has removed remote copies. For cloud erasure, use the installed integration's documented purge and synchronization process, then verify the remote result. Preserve local provenance and backups according to the user's preferences.

## Optional research and fact-checking

The reference Codex setup used Exa for search and Lenz for fact-checking. These connections are separate from routing and learning. Configure them with the target account's supported connector or MCP setup if needed, and verify availability in a fresh session. Check the smallest non-sensitive claims with Lenz when a consequential decision depends on disputed or uncertain facts. Compare its assessment with primary sources and disclose gaps. Keep connector credentials and host instructions containing private context out of the repo.
