"""Isolated, prepared profile debrief. Never reads workspace assessment profiles."""
import json
import os
from pathlib import Path
from threading import RLock
from time import monotonic
from flask import Blueprint, jsonify, render_template, request
from presentation_visuals import charts, profile_presentation
from presentation_bundle import bundle_presentation
from playback_logging import logger
from playback_event_tracker import PlaybackEventTracker
from tavus_client import TavusClient

SCRIPT_PATH = Path(__file__).resolve().parent / 'content/presentation.json'
PRESENTATION_BUDGET = 15 * 60
PRESETS = {'amethyst': SCRIPT_PATH.parent / 'presentations/amethyst.json'}

class Presentation:
    def __init__(self, client=None, clock=monotonic):
        self.client = client or TavusClient()
        self.client.pal_id = os.getenv('XQ_PRESENTATION_TAVUS_PAL_ID') or self.client.pal_id
        self.client.on_playback_event = self.on_playback
        self.client.on_system_event = self.on_system
        self.chapters = json.loads(SCRIPT_PATH.read_text())
        profile = json.loads(SCRIPT_PATH.with_name('presentation_profile.json').read_text())
        self.visuals = charts(profile)
        self.source = profile['source']
        self.revision = 0
        self.clock = clock
        self.lock = RLock()
        self.busy = False
        self.started_at = None
        self.index = 0
        self.completed = False
        self.tracker = PlaybackEventTracker()
        self.retired = set()
        self.shutdown_reason = None

    def status(self):
        with self.lock:
            remaining = PRESENTATION_BUDGET if self.started_at is None else max(0, int(PRESENTATION_BUDGET - (self.clock()-self.started_at)))
            active = bool(self.client.conversation_id)
            replica_ids = getattr(self.client, 'pal_participant_ids', set())
            return dict(active=active, connected=self.client.connected, busy=self.busy,
                        index=self.index, completed=self.completed,
                        replica_participant_ids=sorted(replica_ids) if isinstance(replica_ids, (set, list, tuple)) else [],
                        pending=self.tracker.utterance_id is not None,
                        speaking=self.tracker.inference_id is not None,
                        remaining_seconds=remaining, shutdown_reason=self.shutdown_reason,
                        chapters=self.chapters, visuals=self.visuals, source=self.source, revision=self.revision,
                        word_count=sum(len(c['text'].split()) for c in self.chapters))

    def configure(self, profile, preset=None):
        with self.lock:
            if self.busy or self.client.conversation_id:
                raise ValueError('End the presentation before changing its source.')
            if preset is not None:
                if not isinstance(preset, str) or preset not in PRESETS:
                    raise ValueError('Unknown prepared presentation.')
                if profile is not None:
                    raise ValueError('Choose a prepared presentation or an upload.')
                profile = json.loads(PRESETS[preset].read_text())
            if profile is None:
                chapters = json.loads(SCRIPT_PATH.read_text())
                recorded = json.loads(SCRIPT_PATH.with_name('presentation_profile.json').read_text())
                visuals, source = charts(recorded), recorded['source']
            elif isinstance(profile, dict) and 'presentation_version' in profile:
                chapters, visuals, source = bundle_presentation(profile)
            else:
                chapters, visuals, source = profile_presentation(profile)
            self.chapters, self.visuals, self.source = chapters, visuals, source
            self.index = 0
            self.completed = False
            self.revision += 1

    def start(self):
        with self.lock:
            if self.busy or self.client.conversation_id:
                raise ValueError('End the existing presentation before starting another.')
            self.busy = True
            self.index = 0
            self.completed = False
            self.shutdown_reason = None
            self.tracker.clear()
            self.retired.clear()
            self.started_at = self.clock()
        try:
            data = self.client.create_conversation(
                conversation_name='XQ Investor Presentation', max_call_duration=PRESENTATION_BUDGET)
            return {key: data[key] for key in ('conversation_id','conversation_url','meeting_token') if key in data}
        finally:
            with self.lock:
                self.busy = False

    def play(self, action):
        with self.lock:
            if self.busy or not self.client.conversation_id or not self.client.connected:
                raise ValueError('Wait for the presentation connection before playing.')
            if self.shutdown_reason or self.status()['remaining_seconds'] == 0:
                raise ValueError('The presentation time budget has ended. End this session to start again.')
            if self.tracker.utterance_id is not None:
                raise ValueError('Wait for the current chapter to finish, or end the presentation.')
            if action not in ('play','next','repeat'):
                raise ValueError('Unknown presentation action.')
            if action == 'next':
                if not self.completed or self.index == len(self.chapters)-1:
                    raise ValueError('There is no completed chapter to advance from.')
                self.index += 1
            self.completed = False
            self.tracker.arm(self.index+1)
            # Preserve ownership if delivery is uncertain; never blindly retry.
            self.client.speak(self.chapters[self.index]['text'])

    def on_playback(self, event):
        with self.lock:
            if self.busy or self.shutdown_reason or not self.client.conversation_id:
                return
            if event.get('conversation_id') not in (None, self.client.conversation_id):
                return
            inference = event.get('inference_id')
            if inference in self.retired:
                return
            finished = self.tracker.handle_event(event)
            if finished is not None:
                self.retired.add(inference)
                self.completed = True
            elif event.get('event_type') == PlaybackEventTracker.STOPPED and self.tracker.utterance_id is None:
                if inference:
                    self.retired.add(inference)

    def on_system(self, event):
        with self.lock:
            if not self.client.conversation_id or event.get('conversation_id') not in (None, self.client.conversation_id):
                return
            reason = (event.get('properties') or {}).get('shutdown_reason')
            self.shutdown_reason = reason or self.shutdown_reason or 'conversation_ended'
            self.client.connected = False
            self.tracker.clear()

    def end(self):
        with self.lock:
            if self.busy:
                raise ValueError('A connection change is already in progress.')
            self.busy = True
        try:
            self.client.end_conversation()
            with self.lock:
                self.tracker.clear()
                self.started_at = None
                self.completed = False
                self.shutdown_reason = None
        finally:
            with self.lock:
                self.busy = False

def create_presentation_blueprint(presentation=None):
    blueprint = Blueprint('presentation', __name__)
    instance = presentation
    instance_lock = RLock()

    def current():
        nonlocal instance
        with instance_lock:
            if instance is None:
                instance = Presentation()
            return instance

    @blueprint.get('/presentation')
    def page():
        return render_template('presentation.html')

    @blueprint.get('/api/presentation/status')
    def status():
        response = jsonify(current().status())
        response.headers['Cache-Control'] = 'no-store'
        return response

    @blueprint.post('/api/presentation/<action>')
    def action(action):
        try:
            session = current()
            if action == 'source':
                if request.content_length is None or request.content_length > 1_000_000:
                    return jsonify(error='Choose a profile JSON smaller than 1 MB.'), 413
                data = request.get_json()
                if not isinstance(data, dict) or 'profile' not in data:
                    return jsonify(error='Supply a profile object, or null for the recorded example.'), 400
                try:
                    session.configure(data['profile'], preset=data.get('preset'))
                except (ValueError, TypeError, KeyError, AttributeError) as error:
                    return jsonify(error=str(error)), 400
                return jsonify(ok=True)
            if action == 'start':
                return jsonify(conversation=session.start())
            if action == 'end':
                session.end()
            elif action in ('play','repeat','next'):
                session.play(action)
            else:
                return jsonify(error='Unknown presentation action.'), 404
            return jsonify(ok=True)
        except ValueError as error:
            return jsonify(error=str(error)), 409
        except Exception:
            logger.exception('Presentation service failed')
            return jsonify(error='Presentation service unavailable. End the session before retrying; check the server diagnostics.'), 502
    return blueprint
