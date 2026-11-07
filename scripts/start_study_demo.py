"""Start this checkout's study UI and open the browser after it is ready."""
import json
import os
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8501'
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def study_is_running():
    try:
        with HTTP.open(URL + '/api/bootstrap', timeout=2) as response:
            state = json.load(response)
        return (state.get('data') == 'study'
                and Path(state.get('question_bank_directory', '')).resolve()
                == (ROOT / 'data/question_bank').resolve())
    except (OSError, ValueError, urllib.error.URLError):
        return False


def open_page():
    try:
        opened = webbrowser.open(URL)
    except OSError:
        opened = False
    if not opened:
        print('Open this address in your browser: ' + URL, flush=True)


def main():
    os.chdir(ROOT)
    if study_is_running():
        print('AnotherMe is already running: ' + URL, flush=True)
        open_page()
        return

    stopped = threading.Event()

    def open_when_ready():
        for _ in range(60):
            if stopped.wait(.5):
                return
            if study_is_running():
                open_page()
                return
        print('If the server has started, open: ' + URL, flush=True)

    threading.Thread(target=open_when_ready, daemon=True).start()
    from aitown.cli import main as serve
    sys.argv = ['aitown', 'ui', '--data', 'study', '--port', '8501']
    try:
        serve()
    finally:
        stopped.set()


if __name__ == '__main__':
    main()
