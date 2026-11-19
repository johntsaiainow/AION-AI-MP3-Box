#!/bin/sh
set -eu

MAC="0C:C4:13:41:53:EA"
MAX_ATTEMPTS=6
DELAY=10

echo "AION Bluetooth Auto-Reconnect starting"

controller_available() {
    bluetoothctl --timeout 3 list | grep -q '^Controller '
}

if ! controller_available; then
    # The Broadcom UART can register hci0 but fail initialization at boot.
    driver=/sys/bus/serial/drivers/hci_uart_bcm
    set -- "$driver"/serial*
    if [ "$#" -eq 1 ] && [ -L "$1" ]; then
        device=${1##*/}
        echo "AION: Retrying Broadcom Bluetooth controller initialization"
        printf '%s' "$device" > "$driver/unbind"
        printf '%s' "$device" > "$driver/bind"
        for delay in 1 2 3 4 5 6; do
            if controller_available; then
                break
            fi
            sleep 2
        done
    fi
    if ! controller_available; then
        echo "AION: No Bluetooth controller available" >&2
        exit 1
    fi
fi

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
