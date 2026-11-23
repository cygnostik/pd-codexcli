# Codex learning on this machine

Learning accepts main-thread transcripts whose provider is `openai` or `router`, supporting [codex-router](../../docs/router.md). A transcript label only identifies the configured provider name. Use `router` with a provider configuration you trust. The isolated reviewer still uses its own direct OpenAI configuration. Transcript location, session identity, workspace scope, completion, and subagent checks remain in force.

The original installation used Codex CLI 0.170.0 and four user hooks from `~/.codex/hooks.json`. Only their four exact native trust hashes were registered in `~/.codex/config.toml`. The daemon accepted the configuration reload while the original session stayed open. Native Codex memory was disabled and had zero extracted memories at installation. No old transcripts were imported. The November 23 routing update used Codex CLI 0.171.0. Both synthetic provider tests passed with the installed offline reviewer after earlier runs reported an offline reviewer error.

## What happens during a turn

| Event | Behavior |
|---|---|
| UserPromptSubmit | Open a durable turn record. Retrieve scoped facts with local 256-dimensional embeddings and text search. When the remote bank is active, add validated remote matches. Inject a small, quoted evidence set. Explicit synthesis requests can trigger low-budget reflection. |
| PreToolUse | Look up applicable scoped lessons. For Bash, enforce supported verified flag and input-path corrections and inexpensive literal-path and unmatched-quote checks. A denial tells the model what to correct. A learned suggestion never executes a replacement command. |
| PostToolUse | Record a compact result. Match shell outcomes to native command IDs. The hook can publish supported mechanically verified corrections during the same turn. |
| Stop | Queue one job per main session and turn. A worker waits for the native completion record, projects this turn, reviews it, saves the decision and applies validated changes. Reviewer sessions disable hooks. The user systemd timer retries failures every two minutes when due and recovers missed Stop dispatch for already registered turns. |

The native user skill [codex-learned-procedures](../skills/codex-learned-procedures/SKILL.md) is the discovery entry. Generated project skills live under `~/.local/state/codex-learning/skills/<project>/`. Prompt and tool hooks read current records directly, including changes made after the thread started. The reviewer can attach local additions under an existing skill topic. Automatic writers have no interface for creating executable files or changing hooks, tokens, permission settings, or budgets.

## Review and cost

The primary reviewer uses the existing ChatGPT Pro account through an ephemeral Codex app-server thread with standard `gpt-6-luna`, low reasoning, no working tools and no API-key billing. Its standard credit rates for uncached input and output are each 1/80 of the configured main model's rates. The installation uses a separate profile and temporary workspaces for live tests. [Individual Codex pricing](https://learn.chatgpt.com/docs/pricing?codex-pricing-plans=individual)

Review is limited to 48 attempts per rolling day. One normal turn produces one model review. OpenAI review input is capped at 24,000 UTF-8 bytes of projected data, output at 16,000 accepted characters and the RPC at 60 seconds. Prompt overhead, hidden reasoning and concurrent account activity prevent an exact per-request dollar ceiling on this CLI. The worker cannot purchase credits. It checks the current account, transport, model and allowance before sending review data.

At the verified account's allowance threshold, an offline Qwen2.5-1.5B-Instruct Q4_K_M reviewer can select source evidence. A fixed local validator accepts verbatim user assertions and a small set of demonstrated read-only workflows. The local model takes approximately 1.1 GiB on disk, uses four low-priority CPU threads, an 8,192-token context, at most 700 generated tokens and a 120-second timeout. Check each decision's reviewer_model. Other outages leave work queued. [Qwen model](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)

Compact failure records include redacted evidence and native references. Large turns can exceed the excerpt limit. Inspect the review's coverage field and `codex-learning failures` in that case. Successful command stdout is suppressed except for selected verification values. Some tool/provider paths omit native outcomes, and semantic errors still need recognizable evidence. Within-turn blocking covers supported deterministic checks. Other procedures become available after review. Turns without a persistent native transcript cannot be reviewed. A crash between external inference and saving its response can require another inference. Application of the saved decision is replayable.

## Memory and privacy

`~/.local/state/codex-learning/memory.sqlite3` holds versioned facts and search indexes. `learning.db` holds queue checkpoints, decisions, scoped procedures and mechanical rules. The bank identity incorporates the Unix user, Codex profile/account, machine, and Git root or exact workspace outside Git. Automatic records use project scope. An operator can use `memory --scope user` or `--scope environment` for deliberate local sharing. Memory corrections use stable keys and observation times. Fresh processes can query a committed record immediately.

The Hindsight bank is **codexcli**. Run `codex-learning connect` in a terminal for a hidden credential prompt and immediate connection test. To rotate an exposed key, create a replacement with access to this bank and run `codex-learning connect --replace-key` in a terminal. Keep the old key active until the command verifies tenant continuity and the replacement. Then revoke the exposed key in Hindsight. The local timer detects a private `~/.config/codex-learning/hindsight.key`, verifies the bank, ingests and recalls an artificial fact, and confirms deletion of its document by ID before enabling synchronization. The default HTTPS origin is `https://api.hindsight.vectorize.io`. For a different authorized origin, configure `base_url` in `~/.config/codex-learning/hindsight.json` before activation. `codex-learning hindsight status` reports the actual connection state. A missing key leaves local semantic memory operational.

After activation, new project facts and skill pointers, timestamps, hashed provenance, scope tags and confidence can leave this machine for Hindsight. Remote retrieval sends bounded keywords. Returned records must match this integration, scope and current local revision. Existing untagged bank content is excluded. The local canonical index suppresses superseded and deleted versions while remote writes complete. Routine automatic retrieval uses low-budget Recall. A synthesis request can trigger low-budget Reflect under the prompt hook deadline. Running `codex-learning memory reflect "question"` explicitly uses high-budget Hindsight Reflect with up to 450 output tokens and a 30-second request deadline. Only responses supported by current scoped documents enter the result. The main model can synthesize local evidence while the service is unavailable. Hindsight extraction and reflection can consume the service account's credits. The installation sets rolling daily caps of 48 writes, 144 recalls and four reflections. Keep the local state for provenance and recovery.

Routine local recall, embeddings, and local review send no data externally. The main agent receives retrieved records through its existing OpenAI session. Primary reviews send bounded, redacted turn evidence to the same OpenAI account. Secret detection cannot identify every unlabeled private string.

The article uses SDK run instructions and tools. This installation uses native CLI turn events and scoped Hindsight HTTP operations. It avoids the coding-agent package's broad conversation ingestion. [Hindsight article](https://hindsight.vectorize.io/blog/2026/04/17/openai-agents-persistent-memory) · [Current Hindsight coding-agent integration](https://hindsight.vectorize.io/sdks/integrations/coding-agents) · [Codex hook behavior](https://learn.chatgpt.com/docs/hooks)

## Operator commands

Run these in the relevant workspace. `memory --cwd /absolute/project` selects another workspace.

| Operation | Command |
|---|---|
| Status and account allowance | `codex-learning status` and `codex-learning allowance` |
| Recent decisions, failures and guard rules | `codex-learning reviews`, `codex-learning failures`, `codex-learning guards` |
| Pause learning, resume, retry pending work | `codex-learning pause`, `codex-learning resume`, `codex-learning retry` |
| Inspect a procedure or undo its latest revision | `codex-learning skills "task or command"`, `codex-learning rollback-skill NAME` |
| Remove a specific flag guard | `codex-learning forget-guard 'literal bad command'` |
| Inspect facts or export with provenance | `codex-learning memory list`, `codex-learning memory export --history` |
| Correct or roll back a fact | `codex-learning memory correct KEY 'new value'`, `codex-learning memory rollback KEY` |
| Delete all revisions of a fact | `codex-learning memory delete KEY` |
| Also scrub matching learning-queue records | `codex-learning memory purge KEY` |
| Force Hindsight activation or advance its outbox | `codex-learning hindsight activate`, `codex-learning hindsight sync` |
| Replay isolated, unmetered reliability tests | `python3 -I ~/.local/lib/codex-learning/self_test.py` |
| Rerun live CLI acceptance with real ChatGPT usage | `python3 -I ~/.local/lib/codex-learning/live_test.py` |
| Uninstall, preserving private state | `codex-learning uninstall` |
| Uninstall and erase local learning state and saved Hindsight key | `codex-learning uninstall --purge` |

Pause stops new collection and queue dispatch. A review already in flight can finish. Known preflight guards continue to protect commands. Durable pending work can be retried after a restart. For cloud erasure, purge the intended keys and allow the Hindsight outbox to finish before uninstalling. Uninstall leaves the shared cloud bank and native Codex history alone.

## Acceptance evidence from this installation

| Tests | Observed result |
|---|---|
| 1, 2, 11 | Nine real completed CLI turns produced nine reviewer attempts. An ordinary greeting stored no fact or skill. Reviewer activity produced no main-turn jobs. |
| 3 | A real sort check and line-count validation produced the project-specific Northwind manifest skill. |
| 4, 5, 6 | A misspelled ls flag exited 2, the corrected flag exited 0, and the repeat was denied. Three turns in one continuously loaded process updated the same skill for sort, blocked another bad attempt within the turn, and delivered the updated procedure in the following model request. A separate loopback-backed native test verified relative and absolute path corrections. |
| 7, 8, 9 | A fresh real CLI session returned Seafoam without tools. The unrelated arithmetic turn received no color. After a correction a different fresh thread returned Copper, with no Seafoam in its injected context. A recall question initially caused a redundant revision. A regression replay verifies the assertion filter now rejects question-only evidence. |
| 10 | An immediate local lookup saw the committed fact. Fresh local processes also retrieved a relevant paraphrase without a shared substantive word. |
| 12 | Duplicate concurrent stops and workers produced one review. Concurrency tests covered 48 duplicate fact writes and 40 skill publications. |
| 13 | An actual database obstruction produced a visible hook warning. Repair replayed a saved decision and restored recall without repeating inference. Synthetic reviewer failure left the job pending and retry recovered. A live quota gate suppressed OpenAI inference at 99% usage. |

Live acceptance profiles, learned test facts and temporary project files were removed. The installed test programs use disposable workspaces. On November 18, 2026, live Hindsight Cloud activation on `codexcli` passed asynchronous retain, scoped recall and deletion by document ID. A separate exercise verified a corrected fact superseded the old value, low-budget Reflect referenced two artificial facts, and the explicit high-budget CLI command returned a synthesis in 4.9 seconds. The test documents were removed and their absence verified by ID. Hindsight Cloud 1.2.1 uses the bank config endpoint for identity. Its retired profile endpoint returns HTTP 410.
