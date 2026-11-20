---
name: manage-nginx
description: Manage nginx for the Hermes server, including configuration changes and verification.
---

# Manage nginx

Read [the nginx configuration tracker](/root/hermes-server/config/nginx.json) before making changes. It records observed and desired state; it is not the service's native configuration or proof that changes were applied. Verify current state first. After each change, update the tracker to reflect the actual verified state, including failures or pending work. Never put secrets in it.

Preserve unrelated virtual hosts. Forward the correct Host and HTTPS scheme and support WebSocket upgrades. Test configuration before reload; verify proxy and authentication after changes.

For the IP download site, consult the tracker for the current address, paths, and certificate. Its address-specific listeners require the IP to be present before nginx starts. Preserve its ACME HTTP-01 route and HTTPS redirect when editing; test the actual download, TLS, and unrelated sites after changes. Confirm external reachability separately from local tests.
