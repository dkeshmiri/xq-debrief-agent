"""Local Kokoro synthesis shared by workspaces; no network or profile files."""
import io
import os
import wave
import subprocess
import json
import base64
import atexit
import hashlib
from uuid import uuid4
from queue import Queue, Empty
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock, Thread


class KokoroSpeech:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='kokoro')
        self.lock = Lock()
        self.model = None
        self.cache = OrderedDict()
        self.voice = os.getenv('XQ_KOKORO_VOICE', 'af_heart')
        self.process = None
        self.replies = None
        self.warm_future = None
        self.prefetches = set()
        atexit.register(self.close)

    def close(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
        self.warm_future = None

    def ready(self):
        self.warmup().result()

    def warmup(self):
        with self.lock:
            if self.warm_future is None or (self.warm_future.done() and (
                self.warm_future.exception() is not None or self.process is None or self.process.poll() is not None
            )):
                self.warm_future = self.pool.submit(self._request_worker, {'action': 'warmup'})
            return self.warm_future

    def _load(self):
        if self.model is None:
            from kokoro_onnx import Kokoro
            import onnxruntime as ort
            folder = Path(__file__).resolve().parent / 'models/kokoro'
            model_name = os.getenv('XQ_KOKORO_MODEL', 'kokoro-v1.0.onnx')
            if not all((folder / name).is_file() for name in (model_name, 'voices-v1.0.bin')):
                raise RuntimeError('Kokoro model files are missing. Run scripts/setup_kokoro.py first.')
            options = ort.SessionOptions()
            ort.disable_telemetry_events()
            options.intra_op_num_threads = int(os.getenv('XQ_KOKORO_THREADS', str(min(4, os.cpu_count() or 1))))
            session = ort.InferenceSession(str(folder / model_name), sess_options=options,
                                           providers=['CPUExecutionProvider'])
            self.model = Kokoro.from_session(session, str(folder / 'voices-v1.0.bin'))

    def _synthesize_native(self, text):
        import numpy as np
        self._load()
        samples, rate = self.model.create(text, voice=self.voice, speed=1.0, lang='en-us')
        # Remove only leading/trailing silence; keep a short natural boundary pause.
        audible = np.flatnonzero(np.abs(samples) > 0.003)
        if len(audible):
            samples = samples[max(0, audible[0]-int(rate*.02)):audible[-1]+int(rate*.06)+1]
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes((np.clip(samples, -1, 1)*32767).astype('<i2').tobytes())
        return stream.getvalue()

    def _cache_path(self, text):
        cache = Path(__file__).resolve().parent / '.cache/kokoro'
        key = hashlib.sha256(json.dumps(['kokoro-0.6.1-trim-v1', self.voice,
            os.getenv('XQ_KOKORO_MODEL', 'kokoro-v1.0.onnx'), text]).encode()).hexdigest()
        return cache / (key+'.wav')

    def _request_worker(self, payload):
        root = Path(__file__).resolve().parent
        if self.process is None or self.process.poll() is not None:
            executable = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
            python = os.getenv('XQ_KOKORO_PYTHON', str(root / '.venv-kokoro' / executable))
            if not Path(python).is_file():
                raise RuntimeError('Kokoro runtime is missing. See LOCAL_SPEECH.md for setup.')
            temporary = root / '.cache/tmp'
            temporary.mkdir(parents=True, exist_ok=True)
            self.process = subprocess.Popen([python, '-u', str(root / 'kokoro_worker.py')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                env={**os.environ, 'TMPDIR': str(temporary), 'TEMP': str(temporary), 'TMP': str(temporary)})
            self.replies = Queue()
            Thread(target=self._read_replies, args=(self.process.stdout, self.replies), daemon=True).start()
        self.process.stdin.write(json.dumps({**payload, 'voice': self.voice})+'\n')
        self.process.stdin.flush()
        try:
            line = self.replies.get(timeout=90)
        except Empty:
            self.close()
            raise RuntimeError('Kokoro took too long to generate speech. End the session and retry.')
        if not line:
            raise RuntimeError('Kokoro worker stopped unexpectedly.')
        result = json.loads(line)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    def _synthesize(self, text):
        path = self._cache_path(text)
        if path.is_file():
            return path.read_bytes()
        result = self._request_worker({'text': text})
        audio = base64.b64decode(result['audio'])
        cache = path.parent
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = cache / (uuid4().hex+'.partial')
        try:
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
                output.write(audio)
            temporary.replace(path)
            # Bounded, private cache; only prune clips written by this component.
            clips = sorted(cache.glob('*.wav'), key=lambda p:p.stat().st_mtime, reverse=True)
            total = 0
            for clip in clips:
                total += clip.stat().st_size
                if total > 256 * 1024 * 1024:
                    clip.unlink(missing_ok=True)
        except OSError:
            temporary.unlink(missing_ok=True)  # A read-only cache must not block speech.
        return audio

    @staticmethod
    def _read_replies(stream, replies):
        for line in stream:
            replies.put(line)
        replies.put('')

    def prefetch(self, text):
        return self.audio(text, speculative=True)

    def cancel_prefetch(self):
        with self.lock:
            for future in self.prefetches:
                future.cancel()
            self.prefetches = {future for future in self.prefetches if not future.done()}

    def audio(self, text, *, speculative=False):
        with self.lock:
            future = self.cache.get(text)
            if not speculative:
                # Drop queued lookahead before a question/resumption. In-flight
                # inference cannot be preempted, but queued speculation can.
                for queued in self.prefetches:
                    if queued is not future:
                        queued.cancel()
                self.prefetches.discard(future)
            self.prefetches = {pending for pending in self.prefetches if not pending.done()}
            if future is None or future.cancelled() or (future.done() and future.exception() is not None):
                path = self._cache_path(text)
                if path.is_file():
                    # Cached clips must never wait behind unrelated CPU synthesis.
                    future = Future()
                    future.set_result(path.read_bytes())
                else:
                    future = self.pool.submit(self._synthesize, text)
                    if speculative:
                        self.prefetches.add(future)
                self.cache[text] = future
            self.cache.move_to_end(text)
            while len(self.cache) > 16:
                self.cache.popitem(last=False)
            return future


speech = KokoroSpeech()
