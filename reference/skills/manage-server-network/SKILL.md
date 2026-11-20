---
name: manage-server-network
description: Inspect or change IP addresses and persistent network configuration on the Hermes server.
---

# Manage server network

Read [the network configuration tracker](/root/hermes-server/config/network.json) and verify live addresses, routes, interface and persistent configuration before changes; the tracker is an observation, not proof of current state. Confirm provider allocation and availability before adding an address; subnet membership alone does not establish either. Preserve the management connection and default route. Update the tracker after changes with verified results and pending checks.

For a secondary address, account for both the running interface and persistent network configuration. Validate the persistent configuration before applying it, and avoid restarting networking unnecessarily. Confirm service bindings, firewall and external reachability separately. After a reboot or network change, verify that nginx can bind its address-specific listeners and that existing services remain reachable.
