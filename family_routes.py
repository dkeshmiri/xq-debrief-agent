"""Family comparisons are detached from the single-person playback lifecycle."""
from threading import BoundedSemaphore

from flask import Blueprint, current_app, jsonify, render_template, request

from comparison_engine import ComparisonEngine
from family_group import FamilyGroupEngine, validate_member_ids


class FamilySelectionError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def create_family_blueprint(*, roster_snapshot, pair_snapshot, reasoner_factory,
                            group_snapshot=None, group_reasoner_factory=None, experience='family'):
    blueprint = Blueprint("family", __name__)
    comparison_engine = ComparisonEngine()
    # Family reasoning never takes the playback lock while waiting on a model.
    reasoning_slot = BoundedSemaphore(1)

    def selection():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise FamilySelectionError("Choose two family members.")
        ids = [body.get(key) for key in ("person_a_id", "person_b_id")]
        if any(not isinstance(value, str) or not value.strip() for value in ids):
            raise FamilySelectionError("Choose two family members.")
        if ids[0] == ids[1]:
            raise FamilySelectionError("Choose two different family members.")
        return body, pair_snapshot(*ids)

    @blueprint.get('/team' if experience == 'business' else '/family')
    def page():
        return render_template('business/team.html' if experience == 'business' else 'family.html')

    @blueprint.get("/api/family")
    def roster():
        return jsonify(roster_snapshot())

    @blueprint.post("/api/family/compare")
    def compare():
        _, (persona_a, persona_b) = selection()
        return jsonify(comparison=comparison_engine.create_detached_packet(persona_a, persona_b))

    @blueprint.post("/api/family/question")
    def question():
        body, (persona_a, persona_b) = selection()
        text = body.get("question")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise FamilySelectionError("Enter a comparison question of 1–2,000 characters.")
        if not reasoning_slot.acquire(blocking=False):
            return jsonify(error="A family question is already being answered. Try again shortly."), 409
        try:
            reasoner = reasoner_factory()
            # Resolve domain before any model request; broad questions need clarification.
            reasoner.resolve_comparison_domain(text.strip())
            result = reasoner.answer_question(text.strip(), persona_a, persona_b)
            if result.validation_issues:
                return jsonify(error=result.response), 422
            return jsonify(answer=result.response, domain=result.resolved_domain.value)
        except ValueError as error:
            raise FamilySelectionError(str(error)) from error
        except Exception:
            current_app.logger.exception("Family comparison reasoning failed")
            return jsonify(error="The family comparison service is unavailable. Your profile comparison is still available; try the question again."), 503
        finally:
            reasoning_slot.release()

    def group_selection(question=False):
        body = request.get_json(silent=True)
        allowed = {'person_ids', 'question'} if question else {'person_ids'}
        if not isinstance(body, dict) or set(body) - allowed:
            raise FamilySelectionError('Use assessment profiles only. Experimental context is not enabled.')
        try:
            ids = validate_member_ids(body.get('person_ids'))
        except ValueError as error:
            raise FamilySelectionError(str(error)) from error
        if group_snapshot is None:
            raise FamilySelectionError('Group comparisons are unavailable.', 503)
        return body, group_snapshot(ids)

    @blueprint.post('/api/family/group/compare')
    def compare_group():
        _, personas = group_selection()
        return jsonify(comparison=FamilyGroupEngine().compare(personas))

    @blueprint.post('/api/family/group/question')
    def question_group():
        body, personas = group_selection(question=True)
        text = body.get('question')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise FamilySelectionError('Enter a comparison question of 1–2,000 characters.')
        if group_reasoner_factory is None:
            raise FamilySelectionError('Group reasoning is unavailable.', 503)
        if not reasoning_slot.acquire(blocking=False):
            return jsonify(error='A family question is already being answered. Try again shortly.'), 409
        try:
            result = group_reasoner_factory().answer_question(text.strip(), personas)
            if result.validation_issues:
                return jsonify(error=result.response), 422
            return jsonify(answer=result.response, domain=result.resolved_domain.value)
        except ValueError as error:
            raise FamilySelectionError(str(error)) from error
        except Exception:
            current_app.logger.exception('Family group reasoning failed')
            return jsonify(error='The family comparison service is unavailable. Your assessment tables remain available; try the question again.'), 503
        finally:
            reasoning_slot.release()

    @blueprint.errorhandler(FamilySelectionError)
    def invalid_selection(error):
        return jsonify(error=str(error)), error.status

    @blueprint.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        if experience == 'business' and response.is_json:
            data = response.get_json()
            if isinstance(data, dict) and isinstance(data.get('error'), str):
                data['error'] = data['error'].replace('family member', 'team member').replace('family question', 'team question').replace('family comparison', 'team comparison')
                response.set_data(current_app.json.dumps(data))
        return response

    return blueprint
