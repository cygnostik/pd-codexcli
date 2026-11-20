---
name: manage-certbot
description: Manage certbot for the Hermes server, including configuration changes and verification.
---

# Manage certbot

Read [the certbot configuration tracker](/root/hermes-server/config/certbot.json) before making changes. It records observed and desired state; it is not the service's native configuration or proof that changes were applied. Verify current state first. After each change, update the tracker to reflect the actual verified state, including failures or pending work. Never put secrets in it.

Verify domain DNS and inbound validation reachability before issuance. Track certificate domain, paths, renewal mechanism and verification results; never store private keys or account credentials in the tracker.

For IP certificates, consult the tracker and check current client and CA support. On this host the system Certbot and the newer client used by certbot.timer are separate; inspect the systemd override before changing either. The IP certificate uses the short-lived profile and needs frequent automatic renewal, an HTTP-01 webroot reachable at the IP, and a deploy hook to reload nginx. Validate renewal for both the IP and existing domain certificates after renewal configuration changes. An IP certificate requires verification of the assigned address and inbound reachability rather than DNS for that IP.
