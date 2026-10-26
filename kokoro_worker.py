"""Persistent Python 3.12/3.13 speech worker; stdin/stdout are private IPC."""
import base64
import contextlib
import json
import sys
from local_speech import KokoroSpeech

if __name__ == '__main__':
    synthesizer = KokoroSpeech()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            synthesizer.voice = request['voice']
            with contextlib.redirect_stdout(sys.stderr):
                if request.get('action') == 'warmup':
                    synthesizer._load()
                    result = dict(ready=True)
                else:
                    audio = synthesizer._synthesize_native(request['text'])
                    result = dict(audio=base64.b64encode(audio).decode('ascii'))
        except Exception as error:
            result = dict(error=str(error))
        print(json.dumps(result), flush=True)
