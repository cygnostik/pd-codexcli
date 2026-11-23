# Codex router

The reference host moved from the per-session `codex-router` wrapper to whole-home routing on November 23, 2026. New sessions started with plain `codex` in that home use the local `router` provider. Existing threads can retain their original provider, including when resumed.

The observed combination was codex-router **v0.14.0** and Codex CLI **0.171.0** on Linux. The installed router binary matched the upstream Linux amd64 release digest. The upstream guide requires ChatGPT sign-in and documents prebuilt Linux and macOS binaries. Verify compatibility on the target after upgrading either component. [Release](https://github.com/alexei-led/codex-router/releases/tag/v0.14.0) · [Upstream user guide](https://github.com/alexei-led/codex-router/blob/v0.14.0/docs/user-guide.md)

## Start with a wrapper session

1. Install a verified upstream binary for the target platform and run `codex-router version`.
2. Review the example policy and merge the desired settings into your router configuration, typically `~/.config/codex-router/config.json` or the path under `XDG_CONFIG_HOME`. Check model IDs, supported effort levels and compatibility against the target account. The example's price fields are snapshot list prices in USD per million tokens. They supply panel estimates and the comparison used by cost mode. [Example policy](../reference/router/config.example.json)
3. Choose a classifier. For the reference TypeSafe Jev configuration, supply `TYPESAFE_API_KEY` securely. A wrapper can inherit it from the shell. For whole-home services, set `classifiers.jev.envFile` to an absolute path to a private dotenv file containing that variable. The service does not inherit terminal exports. Use a user-owned file with mode `0600`. Jev receives a clipped prompt, recent dialogue and a bounded task-goal summary. Use the documented local Ollama option if that material must stay local. A missing hosted key leaves automatic classification off. [Classifier options](https://github.com/alexei-led/codex-router/blob/v0.14.0/docs/user-guide.md#choose-a-classifier)
4. Run `codex-router`, send a harmless test prompt, then run `codex-router tui` in a second terminal. The panel monitors and controls sessions. `codex-router sessions` lists registered sessions. No Git checkout is needed.

## Enable whole-home routing

Use this mode when the target should route ordinary `codex` launches. First inspect and back up the existing Codex configuration. The dry run shows the configuration change with the token redacted. These examples use the default home and an explicit router config. Adjust both paths for the target, and consistently pass any custom state directory.

```sh
codex-router --config ~/.config/codex-router/config.json setup --home ~/.codex --dry-run
codex-router --config ~/.config/codex-router/config.json setup --home ~/.codex
codex-router service status --home ~/.codex
codex-router --config ~/.config/codex-router/config.json doctor --home ~/.codex
```

Setup adds a loopback Responses provider and a generated token to marked blocks in `config.toml`. It installs an edge and brain through systemd user units on Linux or launchd on macOS. The edge holds the provider port and forwards requests. The brain selects routes and registers sessions. If the brain is down and the edge remains available, requests pass through unchanged. If the edge is down, close affected sessions and restore the listener before resuming. The proxy handles ChatGPT credentials. Keep the port local and the config, token, classifier credentials and state private.

Start a fresh `codex` thread after setup, or use `/new` in an existing process. Check the panel after its first prompt. The Linux reference host had user-service lingering enabled for logout persistence. Verify the target's user-service lifecycle separately if it needs the same behavior. Resolve provider conflicts before proceeding if setup refuses an existing provider or symlink. [Whole-home setup](https://github.com/alexei-led/codex-router/blob/v0.14.0/docs/user-guide.md#route-a-whole-home-setup)

## Routing policy

| Tier | Baseline route |
| --- | --- |
| Micro | GPT-6 Luna, low |
| Low | GPT-6.1 Terra, medium |
| Medium | GPT-6.2 Sol, medium |
| High | GPT-6.2 Astra, high |

Balanced is the default. Medium coding, debugging and review use high effort. High debugging, review and planning use xhigh. Low documentation uses Terra at medium effort. The router also weighs context fit, cache reuse, model compatibility and repeated evidence before switching. Requests such as subagent and compaction calls pass through. Panel dollar figures are list-price estimates. [Configuration fields](https://github.com/alexei-led/codex-router/blob/v0.14.0/docs/configuration.md)

Use the panel to inspect the reason, pause routing, change between cost, balanced and quality, or pin the next turn. The optional upstream Codex plugin provides a `router` skill for these controls and a separately trusted status hook. Its installation is separate from the router executable and the learning hooks. [Plugin installation](https://github.com/alexei-led/codex-router/blob/v0.14.0/docs/user-guide.md#install-the-codex-plugin)

## Verify the route and learning

- Run a synthetic first prompt. Check the selected route and completed reply in the panel or local logs. A footer or a decision line alone only shows the chosen route. When deeper diagnostics are needed, correlate the rewrite and reply records for the same turn.
- Pin medium and high in separate synthetic turns to verify the account can reach Sol and Astra. Then run representative unpinned tasks to evaluate classifier behavior. On the reference host, wrapper logs confirmed pinned Sol and Astra replies, and the whole-home service logged a Jev-selected Luna reply. The learning queue showed completed jobs from a fresh whole-home `codex` thread and a fresh direct OpenAI thread.
- In the test workspace, check `codex-learning status` and the review queue. The learning hook accepts persistent main-thread transcripts labeled `openai` or `router`. Match the router label to a trusted configured provider. The learning reviewer uses a separate direct OpenAI app-server profile, with local CPU review at its quota gate. [Learning operations](../reference/learning/OPERATIONS.md)

## Upgrade, troubleshoot or bypass

- After a binary upgrade, close affected sessions and rerun whole-home setup with the original config, home and state options. Confirm version, service status and a clean-thread smoke test. For a wrapper policy change, start a new wrapper session. For a whole-home policy change, restart the brain and edge using the target service manager and verify the new route. [Service restart commands](https://github.com/alexei-led/codex-router/blob/v0.14.0/docs/user-guide.md#check-and-restart-the-services)
- If the panel is empty, send a first prompt, check that the session uses the `router` provider and confirm both terminals share the same state directory. If it shows pins only, check the classifier configuration and whether the service can load its private env file. `doctor` is read-only and does not validate the key inside that file.
- For a direct comparison, start a fresh thread with `codex -c 'model_provider="openai"'` where the built-in provider and ChatGPT sign-in are available. In one image-generation exercise, routed attempts reported HTTP 404 and a fresh direct thread succeeded. The cause and general tool compatibility are unverified.
- To remove whole-home routing, close the home's sessions and run `codex-router setup --home ~/.codex --undo` using the corresponding installation options. Verify that a new session uses the intended provider. The separate `--purge` option erases router state.

[Upstream update and recovery procedures](https://github.com/alexei-led/codex-router/blob/v0.14.0/docs/user-guide.md#update-or-uninstall)
