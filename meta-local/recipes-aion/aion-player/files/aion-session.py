#!/usr/bin/env python3
"""AION AI MP3 Box local root console session."""

import json
import os
from pathlib import Path
import subprocess
import sys

STATE = Path("/var/lib/aion-audio")
CONFIG = STATE / "config.json"

PYTHON = "/usr/bin/python3"
SETUP = "/usr/bin/aion-setup"
PLAYER = "/usr/bin/aion-player"


def setup_required():
    try:
        with CONFIG.open(encoding="utf-8") as stream:
            config = json.load(stream)

        return not (
            isinstance(config, dict)
            and config.get("setup_complete") is True
        )
    except (OSError, ValueError):
        return True


def session_environment():
    env = os.environ.copy()

    env.update({
        "HOME": "/root",
        "USER": "root",
        "LOGNAME": "root",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "AION_CONFIG_PATH": str(CONFIG),
        "PULSE_SERVER": "unix:/run/aion-pulse/pulse/native",
        "PULSE_COOKIE": str(STATE / ".config/pulse/cookie"),
    })

    return env


def main():
    if os.geteuid() != 0:
        raise PermissionError("The AION console must run as root")

    env = session_environment()

    if setup_required():
        result = subprocess.run(
            [PYTHON, SETUP],
            env=env,
            check=False,
        )

        if result.returncode != 0:
            return 1

        if setup_required():
            print(
                "AION: Setup is not complete.",
                file=sys.stderr,
            )
            return 1

    os.execve(
        PYTHON,
        [PYTHON, PLAYER, "--interactive"],
        env,
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, KeyError, PermissionError) as exc:
        print(
            f"AION session error: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
