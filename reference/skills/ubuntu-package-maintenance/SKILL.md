---
name: ubuntu-package-maintenance
description: Inspect and apply Ubuntu APT updates, check Ubuntu Pro and ESM Apps coverage, review unattended upgrades, and remove unused packages when requested.
---

# Maintain Ubuntu packages

- Confirm the Ubuntu release and package manager. When Ubuntu Pro applies, use `pro status` and `pro security-status` to distinguish enabled coverage from pending updates. Ubuntu Pro attachment, ESM activation, and unattended-upgrades configuration are separate operations.
- For an authorized update, refresh with `apt-get update` and check for failed repository fetches. Preview the matching transaction with `apt-get -s upgrade`. Review held-back packages, additions, removals, and source origins before applying. A distribution upgrade or a transaction that removes packages needs its own scope.
- If cleanup is requested, preview `apt-get -s autoremove` and review the proposed removals before running `apt-get autoremove`. Check kernels, drivers, and packages required by local services. An empty preview is a valid result.
- For unattended updates, inspect `apt-config dump` for effective periodic settings and allowed origins, and check the systemd timers and recent logs where systemd is in use. Verify that the intended ESM origin is eligible. A successful manual upgrade does not establish unattended coverage.
- Recheck pending updates and record installed, held-back, and removed packages. Check for `/var/run/reboot-required` and inspect affected services or `needrestart` if available. Report any restart still required and follow the user's reboot instructions.

[Ubuntu Pro client](https://documentation.ubuntu.com/pro-client/) · [Automatic updates](https://documentation.ubuntu.com/server/how-to/software/automatic-updates/)
