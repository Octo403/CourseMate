"""Supervise the isolated Python backend and Caddy from Windows Task Scheduler."""
import argparse
import ipaddress
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--public-ip', required=True, type=ipaddress.IPv4Address)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    logs = root/'data/hosted-logs'
    logs.mkdir(parents=True, exist_ok=True)
    processes = []
    handles = []
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    commands = [
        ('backend', [sys.executable, '-u', '-m', 'aitown.cli', 'hosted-ui',
                     '--public-origin', f'https://{args.public_ip}', '--directory', str(root/'data/hosted')]),
        ('caddy', [str(root/'tools/caddy/caddy.exe'), 'run', '--config', str(root/'tools/caddy/Caddyfile'), '--adapter', 'caddyfile']),
    ]
    try:
        for name, command in commands:
            output = (logs/f'{name}.log').open('ab', buffering=0)
            handles.append(output)
            processes.append(subprocess.Popen(command, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        while not stopped:
            for process in processes:
                code = process.poll()
                if code is not None:
                    return code or 1
            time.sleep(1)
        return 0
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for output in handles:
            output.close()


if __name__ == '__main__':
    raise SystemExit(main())
