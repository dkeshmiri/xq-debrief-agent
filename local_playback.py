"""Browser audio transport with explicit playback acknowledgements.

Synthesis completion never advances the debrief. Only the owning browser's
matching audio-ended acknowledgement does. Session IDs reject stale tabs.
"""
from threading import Condition
from uuid import uuid4
from flask import Blueprint, Response, jsonify, request
from local_speech import speech
from playback_event_tracker import PlaybackEventTracker
from playback_logging import logger


class LocalPlayback:
    provider = 'kokoro'

    def __init__(self, synthesizer=speech):
        self.speech = synthesizer
        self.condition = Condition()
        self.connected = False
        self.conversation_id = None
        self.voice_user_name = 'XQ Participant'
        self.pal_id = None
        self.on_playback_event = None
        self.revision = 0
        self.pending = None

    def create_conversation(self, **kwargs):
        self.speech.ready()
        with self.condition:
            self.conversation_id = uuid4().hex
            self.connected = True
            self.pending = None
            self._changed()
            return dict(conversation_id=self.conversation_id, conversation_url=None)

    def _changed(self):
        self.revision += 1
        self.condition.notify_all()

    def speak(self, text):
        with self.condition:
            if not self.connected or self.pending:
                raise RuntimeError('Local audio is unavailable or already pending.')
            job = dict(id=uuid4().hex, text=text, started=False, interrupt=False)
            self.pending = job
            job['future'] = self.speech.audio(text)
            job['future'].add_done_callback(lambda _: self._audio_ready(job))
            self._changed()

    def _audio_ready(self, job):
        with self.condition:
            if self.pending is job:
                if job['future'].exception():
                    logger.warning('Kokoro synthesis failed: %s', job['future'].exception())
                self._changed()

    def prefetch(self, texts):
        if not self.pending:
            return
        for text in texts[:2]:
            self.speech.prefetch(text)

    def interrupt(self):
        self.speech.cancel_prefetch()
        with self.condition:
            if self.pending:
                self.pending['interrupt'] = True
                self._changed()

    def disconnect(self):
        self.speech.cancel_prefetch()
        with self.condition:
            self.connected = False
            self.conversation_id = None
            self.pending = None
            self._changed()

    end_conversation = disconnect

    def listen_to_existing_participants(self):
        pass  # Local microphone capture is opt-in in the browser.

    def status(self):
        return dict(connected=self.connected, conversation_id_set=bool(self.conversation_id), provider=self.provider)

    def _validate(self, session):
        if not self.connected or not session or session != self.conversation_id:
            raise ValueError('This local playback session has ended.')

    def command(self, session, after):
        with self.condition:
            self._validate(session)
            self.condition.wait_for(lambda: self.revision != after or not self.connected, timeout=10)
            self._validate(session)
            data = dict(revision=self.revision)
            job = self.pending
            if job:
                data.update(id=job['id'], interrupt=job['interrupt'])
                if job['future'].done():
                    if job['future'].exception():
                        data['error'] = 'Local speech generation failed. End the session and check Kokoro setup.'
                    else:
                        data.update(ready=True, text=job['text'])
            return data

    def audio(self, session, utterance):
        with self.condition:
            self._validate(session)
            job = self.pending
            if not job or job['id'] != utterance or not job['future'].done():
                raise ValueError('This audio is no longer pending.')
            return job['future'].result()

    def acknowledge(self, session, utterance, kind):
        with self.condition:
            self._validate(session)
            job = self.pending
            if not job or job['id'] != utterance:
                raise ValueError('Stale audio acknowledgement.')
            if kind == 'started' and not job['started'] and not job['interrupt']:
                job['started'] = True
                event_type = PlaybackEventTracker.STARTED
            elif kind in ('ended', 'interrupted') and job['started']:
                if kind == 'interrupted' and not job['interrupt']:
                    raise ValueError('Playback completion does not match the requested stop.')
                # A natural audio end can race an operator pause. Preserve the
                # pause and cursor rather than leaving ownership stranded.
                kind = 'interrupted' if job['interrupt'] else 'ended'
                event_type = PlaybackEventTracker.STOPPED
                self.pending = None
            else:
                raise ValueError('Invalid audio acknowledgement.')
            event = dict(event_type=event_type, conversation_id=session, inference_id=utterance,
                         properties=dict(interrupted=kind == 'interrupted'))
        # Never acquire the app playback lock while holding the transport lock.
        if self.on_playback_event:
            self.on_playback_event(event)


def local_playback_blueprint(client):
    blueprint = Blueprint('local_playback', __name__)

    @blueprint.post('/api/local/warmup')
    def warmup():
        client.speech.warmup()
        return jsonify(ok=True)

    @blueprint.get('/api/local/command')
    def command():
        try:
            return jsonify(client.command(request.args.get('session'), int(request.args.get('after', -1))))
        except ValueError as error:
            return jsonify(error=str(error)), 409

    @blueprint.get('/api/local/audio/<utterance>')
    def audio(utterance):
        try:
            return Response(client.audio(request.args.get('session'), utterance), mimetype='audio/wav',
                            headers={'Cache-Control': 'no-store'})
        except ValueError as error:
            return jsonify(error=str(error)), 409

    @blueprint.post('/api/local/ack')
    def acknowledge():
        data = request.get_json() or {}
        try:
            client.acknowledge(data.get('session'), data.get('id'), data.get('kind'))
            return jsonify(ok=True)
        except ValueError as error:
            return jsonify(error=str(error)), 409

    return blueprint
