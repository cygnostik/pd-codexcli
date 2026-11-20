---
name: manage-ufw
description: Manage ufw for the Hermes server, including configuration changes and verification.
---

# Manage ufw

Read [the ufw configuration tracker](/root/hermes-server/config/ufw.json) before making changes. It records observed and desired state; it is not the service's native configuration or proof that changes were applied. Verify current state first. After each change, update the tracker to reflect the actual verified state, including failures or pending work. Never put secrets in it.

Inspect live IPv4 and IPv6 rules and preserve existing access before changing policy. Confirm the active SSH or other management path before enabling UFW. Keep Hermes ports inaccessible publicly unless explicitly authorized. Account for container firewall bypasses and verify effective rules.
