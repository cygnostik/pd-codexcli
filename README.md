# pd-codexcli

A portable setup brief and reference snapshot for reproducing the skills, learning, and memory integration from the original Codex CLI host on another machine.

Clone this repository on the target machine, start Codex in the checkout, and ask it:

> Read SETUP-PROMPT.md and carry out the setup on this machine.

The prompt asks the agent to inspect the target, adapt and test the reference code, and report what works. It is not an unattended installer. The reference is a snapshot of a custom integration, not an official Codex package; APIs and model availability may change. Existing configuration and data must be preserved.

The default Hindsight bank is the target machine's hostname followed by `-cli`, determined on that machine. Credentials, learned records, session history, machine configuration, and the optional offline reviewer model are not included. Hindsight requires a separately supplied credential and can incur usage charges; local operation should remain available without it.

`reference/learning/OPERATIONS.md` describes the original installation and its limitations. Its host paths, fixed bank name, account assumptions and historical test results are reference material, not instructions to copy literally. The server skills also contain host-specific assumptions and must be reviewed before use.
