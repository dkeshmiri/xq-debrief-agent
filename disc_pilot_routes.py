"""Opt-in assessment/report routes, isolated from persona and playback state."""
from concurrent.futures import TimeoutError
from threading import BoundedSemaphore

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request

import disc_pilot_scoring
import disc_scenario_scoring
import disc_hybrid_scoring


def create_disc_pilot_blueprint(synthesizer=None, *, mode='frequency'):
    scorer, name, path, title = {
        'frequency': (disc_pilot_scoring, 'disc_pilot', '/pilot/disc', 'Behavior frequency'),
        'ranking': (disc_scenario_scoring, 'disc_scenario', '/pilot/disc/scenarios', 'Scenario ranking'),
        'hybrid': (disc_hybrid_scoring, 'disc_hybrid', '/pilot/disc/hybrid', 'Hybrid assessment'),
    }[mode]
    blueprint = Blueprint(name, __name__, url_prefix=path)
    speech = synthesizer
    audio_slot = BoundedSemaphore(1)

    @blueprint.before_request
    def enabled():
        if not current_app.config.get('DISC_PILOT_ENABLED', False):
            abort(404)

    @blueprint.get('')
    def page():
        return render_template('disc_pilot.html', mode=mode, title=title,
                               ranking=mode == 'ranking', hybrid=mode == 'hybrid',
                               pilot_endpoint=f'{blueprint.name}.page')

    @blueprint.get('/questionnaire')
    def questions():
        return jsonify(scorer.questionnaire())

    def submission():
        if request.content_length and request.content_length > 16_384:
            abort(413)
        return scorer.score_assessment(request.get_json(silent=True))

    @blueprint.post('/report')
    def report():
        return jsonify(submission())

    @blueprint.post('/audio/<section_id>')
    def audio(section_id):
        nonlocal speech
        result = submission()
        section = next((item for item in result['sections'] if item['id'] == section_id), None)
        if section is None:
            abort(404)
        if not audio_slot.acquire(blocking=False):
            return jsonify(error='A report section is being prepared. Please try again shortly.'), 409
        release_slot = True
        future = None
        try:
            if speech is None:
                from local_speech import KokoroSpeech
                # A separate queue keeps pilot requests out of active debrief playback.
                speech = KokoroSpeech()
            future = speech.audio(section['text'])
            clip = future.result(timeout=100)
            return Response(clip, mimetype='audio/wav')
        except TimeoutError:
            # Hold the slot until the timed-out work exits, avoiding an unbounded queue.
            if future is not None:
                release_slot = False
                future.add_done_callback(lambda _: audio_slot.release())
            return jsonify(error='The voice is taking longer to prepare. Your report is ready to read; try playback again shortly.'), 503
        except Exception:
            current_app.logger.exception('Pilot report speech failed')
            return jsonify(error='Voice playback is unavailable. Your report is ready to read; check the local Kokoro setup and try again.'), 503
        finally:
            if release_slot:
                audio_slot.release()

    @blueprint.errorhandler(ValueError)
    def invalid_submission(error):
        return jsonify(error=str(error)), 400

    @blueprint.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    return blueprint
