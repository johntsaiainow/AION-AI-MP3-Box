#!/bin/sh
set -eu

if [ ! -t 0 ]; then
    echo "ERROR: AION console requires a terminal." >&2
    exit 1
fi

if [ "$(id -u)" != "0" ]; then
    echo "ERROR: Run AION console as root." >&2
    exit 1
fi

exec /usr/bin/python3 -u /usr/bin/aion-session
