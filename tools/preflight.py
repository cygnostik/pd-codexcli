#!/usr/bin/env python3
"""Read-only, credential-free inventory for the setup agent (Python 3.8+)."""
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sys


def inventory():
    system = platform.system()
    try:
        release = platform.release()
    except OSError:
        release = "unknown"
    host = socket.gethostname()
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    router_config = Path(os.environ.get("CODEX_ROUTER_CONFIG") or config_home / "codex-router" / "config.json")
    wsl = system == "Linux" and ("microsoft" in release.lower() or bool(os.environ.get("WSL_DISTRO_NAME")))
    return {
        "platform": system,
        "release": release,
        "wsl_detected": wsl,
        "python_version": platform.python_version(),
        "python_supported": sys.version_info >= (3, 8),
        "hostname": host,
        "proposed_hindsight_bank": host + "-cli",
        "bank_note": "Candidate only: validate service naming rules before use; do not silently substitute another bank.",
        "executables": {name: shutil.which(name) for name in ("codex", "codex-router", "git", "gh", "systemctl", "launchctl")},
        "codex_home": str(codex_home),
        "existing_paths": {"codex_config": (codex_home / "config.toml").is_file(),
                           "codex_hooks": (codex_home / "hooks.json").is_file(),
                           "router_config": router_config.is_file(),
                           "user_skills": (home / ".agents" / "skills").is_dir(),
                           "learning_install": (home / ".local" / "lib" / "codex-learning" / "learn.py").is_file()},
        "stdlib": {name: importlib.util.find_spec(name) is not None for name in ("sqlite3", "fcntl")},
        "note": "Presence is not proof of a working installation, authentication, hook trust, service state, or bank access.",
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2))
