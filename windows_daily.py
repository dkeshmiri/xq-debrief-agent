"""Daily JS transport for native Windows, implementing the app's small SDK surface.

Each call owns a headless Chromium and an asyncio thread. Callbacks run on a
separate thread: they may acquire playback_lock or call transport methods without
blocking Chromium's event loop. No API keys enter the browser.
"""
import asyncio
import base64
import logging
import queue
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
log = logging.getLogger(__name__)


class EventHandler:
    pass


class Daily:
    @staticmethod
    def init():
        pass

    @staticmethod
    def create_native_vad(*, sample_rate, channels, reset_period_ms):
        if sample_rate != 16000 or channels != 1:
            raise ValueError('Windows voice input requires 16 kHz mono PCM.')
        import webrtcvad
        vad = webrtcvad.Vad(2)
        return SimpleNamespace(analyze_frames=lambda pcm: float(vad.is_speech(pcm, sample_rate)))


class CallClient:
    def __init__(self, event_handler):
        self.handler = event_handler
        self.renderers = {}
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.loop = None
        self.page = self.browser = self.playwright = None
        self.thread = threading.Thread(target=self._run, daemon=True, name='xq-daily-browser')
        self.callbacks = threading.Thread(target=self._callbacks, daemon=True, name='xq-daily-events')
        self.thread.start()
        self.callbacks.start()
        if not self.ready.wait(10):
            raise RuntimeError('Windows transport thread did not start.')

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def _submit(self, coroutine, timeout=45):
        if self.closed.is_set():
            coroutine.close()
            raise RuntimeError('The Windows transport is closed.')
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result(timeout)
        except FutureTimeout:
            future.cancel()
            # Sending may have succeeded: callers must never retry Echo blindly.
            raise RuntimeError('Windows transport timed out; end this session before retrying.') from None

    def _receive(self, _source, event):
        if self.closed.is_set():
            return
        # Audio is best effort under overload; canonical control events never drop.
        if event.get('type') == 'audio' and self.events.qsize() > 200:
            return
        self.events.put(event)

    def _callbacks(self):
        while True:
            event = self.events.get()
            if event is None:
                return
            if self.closed.is_set():
                continue
            try:
                self._dispatch(event)
            except Exception:
                log.exception('Windows transport callback failed')

    def _dispatch(self, event):
        kind = event.get('type')
        if kind == 'state':
            self.handler.on_call_state_updated(event['state'])
        elif kind == 'error':
            self.handler.on_call_state_updated('error')
            self.handler.on_error(event.get('message', 'Daily browser error'))
        elif kind == 'message':
            self.handler.on_app_message(event['data'], event['sender'])
        elif kind == 'joined':
            self.handler.on_participant_joined(event['participant'])
        elif kind == 'left':
            self.renderers.pop(event['participant']['id'], None)
            self.handler.on_participant_left(event['participant'], 'left')
        elif kind == 'audio':
            renderer = self.renderers.get(event['id'])
            if renderer:
                pcm = base64.b64decode(event['pcm'], validate=True)
                if len(pcm) != 640:
                    raise ValueError('Expected a 20 ms mono PCM16 frame.')
                renderer(event['id'], SimpleNamespace(audio_frames=pcm, sample_rate=16000,
                                                     num_channels=1), 'microphone')

    async def _open(self, url, token):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True, args=[
            '--autoplay-policy=no-user-gesture-required', '--disable-background-timer-throttling'])
        self.browser.on('disconnected', lambda: self._receive(None, {'type':'state', 'state':'left'}))
        self.page = await self.browser.new_page()
        await self.page.expose_binding('xqTransportEvent', self._receive)
        # A secure loopback origin served entirely in-process; no extra HTTP port.
        await self.page.route('http://127.0.0.1/xq-transport',
                              lambda route: route.fulfill(body='<!doctype html><title>XQ transport</title>',
                                                          content_type='text/html'))
        await self.page.goto('http://127.0.0.1/xq-transport')
        await self.page.add_script_tag(path=str(ROOT / 'static/vendor/daily.js'))
        await self.page.add_script_tag(path=str(ROOT / 'static/windows-daily.js'))
        await self.page.evaluate('args => xqDaily.join(args)', {'url':url, 'token':token})

    def join(self, url, meeting_token=None):
        try:
            self._submit(self._open(url, meeting_token), timeout=60)
        except Exception:
            self.release()
            raise

    async def _evaluate(self, expression, argument=None):
        if self.page is None:
            raise RuntimeError('Daily browser has not joined.')
        return await self.page.evaluate(expression, argument)

    def send_app_message(self, message):
        self._submit(self._evaluate('message => xqDaily.send(message)', message))

    def participants(self):
        return self._submit(self._evaluate('() => xqDaily.participants()'))

    def set_audio_renderer(self, participant_id, callback, *, audio_source, sample_rate,
                           callback_interval_ms):
        if (audio_source, sample_rate, callback_interval_ms) != ('microphone', 16000, 20):
            raise ValueError('Unsupported Windows audio renderer format.')
        self.renderers[participant_id] = callback
        try:
            self._submit(self._evaluate('id => xqDaily.listen(id)', participant_id))
        except Exception:
            self.renderers.pop(participant_id, None)
            raise

    def leave(self):
        if self.page is not None and not self.closed.is_set():
            self._submit(self._evaluate('() => xqDaily.leave()'), timeout=10)

    async def _close(self):
        try:
            if self.browser is not None:
                await self.browser.close()
        finally:
            if self.playwright is not None:
                await self.playwright.stop()

    def release(self):
        if self.closed.is_set():
            return
        try:
            self._submit(self._close(), timeout=15)
        finally:
            self.closed.set()
            self.renderers.clear()
            self.events.put(None)
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)
