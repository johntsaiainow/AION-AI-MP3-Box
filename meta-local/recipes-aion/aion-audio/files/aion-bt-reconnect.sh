#!/bin/sh
set -eu

MAC="0C:C4:13:41:53:EA"
MAX_ATTEMPTS=6
DELAY=10

echo "AION Bluetooth Auto-Reconnect starting"

attempt=1

while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do

    if bluetoothctl info "$MAC" 2>/dev/null |
        grep -q 'Connected: yes'; then
        echo "AION: Pixel already connected"
        exit 0
    fi

    echo "AION: connection attempt $attempt/$MAX_ATTEMPTS"

    if bluetoothctl --timeout 20 connect "$MAC"; then
        echo "AION: connect command completed"
    else
        echo "AION: connect attempt failed"
    fi

    sleep 3

    if bluetoothctl info "$MAC" 2>/dev/null |
        grep -q 'Connected: yes'; then
        echo "AION: Pixel connected successfully"
        exit 0
    fi

    attempt=$((attempt + 1))

    if [ "$attempt" -le "$MAX_ATTEMPTS" ]; then
        sleep "$DELAY"
    fi
done

echo "AION: Bluetooth reconnect failed"
exit 1
