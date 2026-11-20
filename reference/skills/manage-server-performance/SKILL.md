---
name: manage-server-performance
description: Inspect and manage this Ubuntu server's CPU performance, storage I/O, QEMU/KVM, passt networking, and system locale; use for tuning or diagnosing these systems.
---

# Manage server performance

Read `/root/hermes-server/config/server-performance.json` for the last verified state and change history. The tracker is an inventory, not a source of live truth: recheck the host and installed versions before making decisions. Update observed state, changes, verification, and unresolved items after authorized changes; never record credentials, private data, or unnecessary device identifiers.

This is a remotely managed production server with difficult out-of-band access. Preserve existing SSH, network and running services. Prefer reversible live changes and confirm health before making them persistent. Do not alter bootloader, kernel command line, firmware, partitioning, filesystem durability, or network topology as routine tuning. Treat such changes according to their actual risk and user authorization. Do not disable security mitigations for performance. Avoid disruptive or write-heavy benchmarks on its single system SSD; use representative, bounded measurements and report impact.

Before tuning, check system state, pressure and available resources, relevant service ownership, and current configuration. Identify competing managers before writing settings. Make a rollback path and record the previous values. Verify every policy/device affected, service and remote accessibility, and relevant temperature/error counters; note when verification is only a short observation. Prefer measured workload benefits over speculative settings. Don't reboot to validate routine changes.

For operational commands, current configuration, caveats, and rollback see [references/operations.md](references/operations.md). For existing web, firewall, certificates, or Hermes services use their dedicated management skills when applicable. Confirm current vendor and kernel documentation before relying on version-specific behavior.
