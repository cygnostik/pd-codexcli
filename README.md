# pd-codexcli

A portable setup brief and reference snapshot for reproducing the skills, learning, memory, and optional model routing from the original Codex CLI host.

Clone this repository on the target machine, start Codex in the checkout, and ask it:

> Read SETUP-PROMPT.md and carry out the setup on this machine.

For a read-only inventory first, run `python3 tools/preflight.py` (on native Windows, `py tools/preflight.py`). It reports a candidate bank name and checks for tools and existing configuration without reading credentials. Review [platform guidance](docs/platforms.md) and [operations and verification](docs/operations.md) before setup.

The [router guide](docs/router.md) covers the November 2026 move to whole-home routing, the Luna/Terra/Sol/Astra policy, how to verify a route, and how to bypass or undo it. The reusable [policy example](reference/router/config.example.json) can also be used with the single-session wrapper.

The [skills inventory](docs/operations.md#skills) lists the bundled skills, including server performance and Ubuntu package maintenance, and explains where Codex discovers them.

The prompt asks the agent to inspect the target, adapt and test the reference code, and report what works. It is not an unattended installer. The reference is a snapshot of a custom integration, not an official Codex package; APIs and model availability may change. Existing configuration and data must be preserved.

The source snapshot is Linux-oriented and needs adaptation even on another Linux host. macOS and native Windows are not validated ports; WSL is the closest Windows starting point. No platform is installed or changed by the preflight tool.

The default Hindsight bank is the target machine's hostname followed by `-cli`, determined on that machine. Credentials, learned records, session history, machine configuration, and the optional offline reviewer model are not included. Hindsight requires a separately supplied credential and can incur usage charges; local operation should remain available without it.

`reference/learning/OPERATIONS.md` describes the original installation and its limitations. Its host paths, fixed bank name, account assumptions and historical test results are reference material, not instructions to copy literally. The server skills also contain host-specific assumptions and must be reviewed before use.
