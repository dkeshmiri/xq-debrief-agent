"""Exercise a source or packaged server without paid APIs; shuts down afterward."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import urllib.request
import http.cookiejar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    command = [str(args.exe.resolve()), '--serve'] if args.exe else [sys.executable, '-X', 'utf8', str(root / 'windows_launcher.py'), '--serve']
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                             env={**os.environ, 'OPENAI_API_KEY':'test-not-a-real-key',
                                  'TAVUS_API_KEY':'', 'TAVUS_PAL_ID':'', 'XQ_PLAYBACK_PROVIDER':'kokoro'})
    lines = queue.Queue()
    def read():
        for line in child.stdout:
            lines.put(line)
        lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    output = []
    try:
        while True:
            line = lines.get(timeout=60)
            if line is None:
                raise RuntimeError('Server exited: ' + ''.join(output))
            output.append(line)
            if line.startswith('XQ_READY='):
                url = line.strip().split('=',1)[1]
                break
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def get(path):
            with opener.open(url+path, timeout=90) as response:
                return response.read()
        def post(path, payload):
            request = urllib.request.Request(url+path, data=json.dumps(payload).encode(),
                                             headers={'Content-Type':'application/json'})
            with opener.open(request, timeout=90) as response:
                return json.load(response)
        for path in ('/', '/debrief', '/family', '/business/', '/business/debrief',
                     '/static/app.js', '/static/windows-daily.js'):
            assert get(path), path
        access = post('/api/presentation/unlock', {'pin':'2020'})
        assert access['unlocked'], access
        for preset in ('amethyst','workforce-investor','iranian-american','iranian-american-fa'):
            assert post('/api/presentation/source', {'profile':None,'preset':preset})['ok']
            status = json.loads(get('/api/presentation/status'))
            assert status['chapters'], preset
            if preset.endswith('-fa'):
                assert status['language'] == 'fa'
                assert any('\u0600' <= c <= '\u06ff' for c in status['chapters'][0]['text'])
        print('Pages, lazy Workplace import, PIN and all presentation scripts passed.', flush=True)
        # Use the actual packaged Kokoro worker and HTTP playback endpoints.
        started = post('/api/session/start', {})
        assert started['ok'], started
        session = started['conversation']['conversation_id']
        assert post('/api/debrief/speak', {})['ok']
        deadline = time.monotonic() + 90
        after = -1
        while time.monotonic() < deadline:
            command = json.loads(get(f'/api/local/command?session={session}&after={after}'))
            assert not command.get('error'), command
            if command.get('ready'):
                audio = get(f'/api/local/audio/{command["id"]}?session={session}')
                assert audio[:4] == b'RIFF' and len(audio) > 1000
                print(f'Generated PCM WAV: {len(audio)} bytes.', flush=True)
                break
            after = command['revision']
        else:
            raise RuntimeError('Local speech did not become ready.')
        assert post('/api/session/end', {})['ok']
        print('Local speech session warmup/start/end passed.', flush=True)
    finally:
        if child.poll() is None:
            try:
                child.stdin.write('stop\n')
                child.stdin.flush()
            except OSError:
                pass
            try:
                child.wait(timeout=45)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                raise RuntimeError('Server did not shut down cleanly.')
        print('Server exit:', child.returncode, flush=True)
        if child.returncode:
            while not lines.empty():
                line = lines.get()
                if line:
                    print(line, end='')
            raise RuntimeError('Server returned a nonzero exit code.')


if __name__ == '__main__':
    main()
