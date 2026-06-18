"""Task runner for the artifact (spec P0-T1 S3).

Plain-stdlib runner so it works in any venv with zero extra deps. Usage:

    python tasks.py install        # install the pinned stack into the active venv
    python tasks.py test           # run the pytest suite
    python tasks.py profile-data   # P0-T2 — data-quality funnel (not built yet)
    python tasks.py fetch-carbon   # P0-T3 — carbon-intensity acquisition (not built yet)

Commands for modules not yet built (profile-data, fetch-carbon) exit non-zero
with a pointer to the task that creates them, rather than failing silently.
"""

import os
import subprocess
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> int:
    print("+ " + " ".join(cmd))
    return subprocess.call(cmd, cwd=CODE_DIR)


def install() -> int:
    """Install the reproducible lockfile if present, else the top-level deps."""
    lock = CODE_DIR / "requirements.lock.txt"
    req = lock if lock.exists() else CODE_DIR / "requirements.txt"
    return _run([sys.executable, "-m", "pip", "install", "-r", str(req)])


def test() -> int:
    return _run([sys.executable, "-m", "pytest"])


def profile_data() -> int:
    """Run the P0-T2 data-quality funnel + profile (scripts/profile_data.py)."""
    env = {**os.environ, "PYTHONPATH": str(CODE_DIR)}
    print("+ python scripts/profile_data.py")
    return subprocess.call(
        [sys.executable, "scripts/profile_data.py"], cwd=CODE_DIR, env=env
    )


def fetch_carbon() -> int:
    print("fetch-carbon is not implemented yet — created in task P0-T3 "
          "(scheduler_core/carbon.py + code/data/carbon/).")
    return 1


COMMANDS = {
    "install": install,
    "test": test,
    "profile-data": profile_data,
    "fetch-carbon": fetch_carbon,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print("usage: python tasks.py {" + " | ".join(COMMANDS) + "}")
        return 2
    return COMMANDS[argv[0]]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
