"""Remove this installation and detach currently loaded Codex hooks. Keep state by default."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys

home=Path.home()
lib=Path(__file__).resolve().parent
state=home/'.local/state/codex-learning'
link=home/'.local/bin/codex-learning'
units=home/'.config/systemd/user'
skill=home/'.agents/skills/codex-learned-procedures'
if sys.argv[1:] not in ([],['--purge']):
    sys.exit('Usage: codex-learning uninstall [--purge]')
if lib!=home/'.local/lib/codex-learning' or link.resolve()!=lib/'learn.py':
    sys.exit('Installation paths do not match this home')
subprocess.run([sys.executable,'-I',str(lib/'learn.py'),'pause'],check=True)
subprocess.run([sys.executable,'-I',str(lib/'install.py'),'uninstall'],check=True)
timer=units/'codex-learning.timer'
if timer.is_file():
    subprocess.run(['systemctl','--user','disable','--now','codex-learning.timer'],check=True)
with (state/'worker.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    if timer.is_file():
        timer.unlink()
        (units/'codex-learning.service').unlink(missing_ok=True)
        subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    (skill/'SKILL.md').unlink(missing_ok=True)
    if skill.is_dir() and not any(skill.iterdir()): skill.rmdir()
    link.unlink()
    if lib.is_symlink() or state.is_symlink(): sys.exit('Refusing redirected installation paths')
    shutil.rmtree(lib)
if '--purge' in sys.argv:
    shutil.rmtree(state)
    (home/'.config/codex-learning/hindsight.key').unlink(missing_ok=True)
    print('Removed the installation and local learning state.')
else:
    print('Removed the installation. Private records are in',state)
