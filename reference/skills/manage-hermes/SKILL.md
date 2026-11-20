---
name: manage-hermes
description: Manage hermes for the Hermes server, including configuration changes and verification.
---

# Manage hermes

Read [the hermes configuration tracker](/root/hermes-server/config/hermes.json) before making changes. It records observed and desired state; it is not the service's native configuration or proof that changes were applied. Verify current state first. After each change, update the tracker to reflect the actual verified state, including failures or pending work. Never put secrets in it.

Use the upstream installation and dashboard documentation. The selected public authentication approach is self-hosted OIDC; keep public access disabled until it is configured and verified. Run under a dedicated unprivileged service account. Keep the dashboard on loopback, set the exact public URL and verify dashboard authentication is required before exposure. Do not record credentials or tokens in the tracker.
