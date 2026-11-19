#!/usr/bin/env python3
"""AION Bluetooth controller: BlueZ operations and PulseAudio sink selection.
No shell invocation, no automatic pairing, no destructive disk operations.
"""
import argparse
import os
import re
import subprocess
import sys

MAC = re.compile(r'^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')
DEVICE = re.compile(r'^Device\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s*(.*)$')
SINK = re.compile(r'^[A-Za-z0-9_.:-]+$')
ANSI_COLOR = re.compile(r'\x1b\[[0-9;]*m')

class BluetoothError(Exception):
    pass

def run(argv, timeout=20):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BluetoothError(f'{argv[0]} unavailable or timed out: {exc}') from exc
    output = (p.stdout + '\n' + p.stderr).strip()
    if p.returncode:
        raise BluetoothError(output or f'{argv[0]} exited {p.returncode}')
    return output

def bt(*args, timeout=25, agent=None):
    command = ['bluetoothctl']
    if agent:
        command.append(f'--agent={agent}')
    result = ANSI_COLOR.sub('', run([*command, *args], timeout=timeout))
    # bluetoothctl sometimes exits 0 even on an operation failure.
    if re.search(r'(?im)^\s*(?:Failed|Error|No default controller|Invalid command|Device .* not available)\b', result):
        raise BluetoothError(result)
    return result

def address(value):
    if not MAC.fullmatch(value):
        raise BluetoothError('Invalid Bluetooth MAC address')
    return value.upper()

def devices(kind='devices'):
    if kind not in ('devices', 'paired-devices'):
        raise BluetoothError('Invalid device listing')
    result = bt('devices', 'Paired') if kind == 'paired-devices' else bt('devices')
    return [(m.group(1).upper(), m.group(2).strip()) for line in result.splitlines()
            if (m := DEVICE.match(line.strip()))]

def status():
    return bt('show')

def power(on):
    return bt('power', 'on' if on else 'off')

def phone_pairing():
    power(True)
    try:
        bt('pairable', 'on')
        bt('discoverable', 'on')
        subprocess.run(
            ['bluetoothctl', '--agent=DisplayYesNo'],
            timeout=120,
            check=True,
        )
    except subprocess.TimeoutExpired:
        return
    except subprocess.CalledProcessError as exc:
        raise BluetoothError('Phone pairing console exited unexpectedly') from exc
    finally:
        for setting in ('discoverable', 'pairable'):
            try:
                bt(setting, 'off', timeout=5)
            except BluetoothError as exc:
                print(exc, file=sys.stderr)

def scan(seconds=10, transport='on'):
    if not 3 <= seconds <= 30:
        raise BluetoothError('Scan duration must be 3–30 seconds')
    # bluetoothctl --timeout exits when discovery time is up. No background scanning.
    result = run(['bluetoothctl', '--timeout', str(seconds), 'scan', transport], timeout=seconds + 8)
    output = ANSI_COLOR.sub('', result)
    if not re.search(r'(?im)^\s*Discovery started\s*$', output):
        raise BluetoothError(output or 'Bluetooth discovery did not start')
    return result

def device_action(action, mac):
    if action not in ('pair', 'trust', 'connect', 'disconnect', 'remove', 'info'):
        raise BluetoothError('Unsupported Bluetooth operation')
    mac = address(mac)
    if action == 'pair':
        was_pairable = bool(re.search(r'(?m)^\s*Pairable: yes\s*$', status()))
        try:
            if not was_pairable:
                bt('pairable', 'on', timeout=5)
            return bt(action, mac, timeout=65, agent='NoInputNoOutput')
        finally:
            if not was_pairable:
                bt('pairable', 'off', timeout=5)
    return bt(action, mac, timeout=65 if action == 'connect' else 25)

def pulse_environment():
    # PulseAudio runs as aion-audio in this image; do not silently operate
    # against root's private PulseAudio instance.
    runtime = '/run/aion-pulse/pulse/native'
    if not os.path.exists(runtime):
        raise BluetoothError('AION PulseAudio socket not found: ' + runtime)
    return {
        'PULSE_SERVER': 'unix:' + runtime,
        'PULSE_COOKIE': '/var/lib/aion-audio/.config/pulse/cookie',
    }

def pactl(*args):
    env = os.environ.copy()
    env.update(pulse_environment())
    try:
        p = subprocess.run(['pactl', *args], capture_output=True, text=True,
                           timeout=15, stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BluetoothError(f'pactl failed: {exc}') from exc
    if p.returncode:
        raise BluetoothError((p.stderr or p.stdout).strip())
    return p.stdout.strip()

def sinks():
    return pactl('list', 'short', 'sinks')

def set_sink(name):
    if not SINK.fullmatch(name):
        raise BluetoothError('Invalid PulseAudio sink name')
    names = [line.split('\t')[1] for line in sinks().splitlines() if '\t' in line]
    if name not in names:
        raise BluetoothError('Sink is not present in PulseAudio')
    return pactl('set-default-sink', name)

def cli():
    parser = argparse.ArgumentParser(description='AION Bluetooth Management')
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('status', 'on', 'off', 'scan', 'devices', 'paired', 'sinks'):
        sub.add_parser(action)
    for action in ('pair', 'trust', 'connect', 'disconnect', 'remove', 'info'):
        sub.add_parser(action).add_argument('mac')
    sub.add_parser('set-sink').add_argument('name')
    args = parser.parse_args()
    try:
        if args.action == 'status': result = status()
        elif args.action == 'on': result = power(True)
        elif args.action == 'off': result = power(False)
        elif args.action == 'scan': result = scan()
        elif args.action == 'devices': result = '\n'.join(f'{a} {n}' for a,n in devices())
        elif args.action == 'paired': result = '\n'.join(f'{a} {n}' for a,n in devices('paired-devices'))
        elif args.action == 'sinks': result = sinks()
        elif args.action == 'set-sink': result = set_sink(args.name)
        else: result = device_action(args.action, args.mac)
        print(result or 'OK')
    except BluetoothError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(cli())
