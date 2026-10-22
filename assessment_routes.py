"""Independent import routes: no access to active debrief/session state."""
import hmac
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request
from openai import APIError
from pydantic import ValidationError
from werkzeug.exceptions import RequestEntityTooLarge

from assessment_drafts import DraftConflict, DraftStore
from assessment_importer import AssessmentImporter, ImportServiceError, MAX_PDF_BYTES, MAX_REPORTS
from assessment_schema import Extraction, GenerateRequest, OverrideRequest, missing_fields


def create_assessment_blueprint(importer=None, store=None):
    blueprint = Blueprint("assessments", __name__)
    service = importer or AssessmentImporter()

    def drafts():
        return store or DraftStore(current_app.config.get(
            "ASSESSMENT_DRAFT_DIR", Path(current_app.root_path) / "data" / "assessment_drafts"))

    def draft_response(draft):
        facts = Extraction.model_validate(draft["extraction"]).facts
        return jsonify(draft_id=draft["id"], revision=draft["revision"],
                       extraction=draft["extraction"], family_role=draft["family_role"],
                       overrides=draft["overrides"], missing_fields=missing_fields(facts))

    @blueprint.get("/json-maker")
    def page():
        return render_template("json_maker.html")

    @blueprint.post("/api/assessments/extract")
    def extract():
        uploads = request.files.getlist("reports")
        role = request.form.get("family_role", "").strip()
        if not role or len(role) > 100:
            return jsonify(error="Enter a family role of 1–100 characters."), 400
        if not 1 <= len(uploads) <= MAX_REPORTS:
            return jsonify(error=f"Choose 1–{MAX_REPORTS} PDFs for the same person."), 400
        reports = []
        remaining = MAX_PDF_BYTES
        for upload in uploads:
            data = upload.read(remaining + 1)
            remaining -= len(data)
            if remaining < 0:
                raise RequestEntityTooLarge()
            reports.append((upload.filename or "", data))
        result = service.extract(reports)
        return draft_response(drafts().create(result, role))

    @blueprint.get("/api/assessments/<draft_id>")
    def get_draft(draft_id):
        return draft_response(drafts().get(draft_id))

    @blueprint.post("/api/assessments/<draft_id>/override")
    def override(draft_id):
        payload = OverrideRequest.model_validate(request.get_json(silent=True))
        expected = os.getenv("XQ_IMPORT_OVERRIDE_PIN", "2020")
        if not hmac.compare_digest(payload.pin.encode(), expected.encode()):
            return jsonify(error="Incorrect override PIN. Changes were not saved."), 403
        draft = drafts().override(draft_id, payload.revision, payload.facts, payload.family_role)
        return draft_response(draft)

    @blueprint.post("/api/assessments/generate")
    def generate():
        payload = GenerateRequest.model_validate(request.get_json(silent=True))
        draft = drafts().get(payload.draft_id)
        if draft["revision"] != payload.revision:
            raise DraftConflict("The saved review changed. Reload it before generating.")
        result = service.generate(Extraction.model_validate(draft["extraction"]), draft["family_role"])
        drafts().save_generated(payload.draft_id, payload.revision, result)
        return jsonify(result)

    @blueprint.post("/api/assessments/use")
    def use_persona():
        payload = GenerateRequest.model_validate(request.get_json(silent=True))
        save_persona = current_app.config.get("SAVE_ASSESSMENT_PERSONA")
        if save_persona is None:
            return jsonify(error="Profile saving is unavailable."), 503
        filename = drafts().publish(payload.draft_id, payload.revision, save_persona)
        return jsonify(file=filename, next_url="/debrief")

    @blueprint.errorhandler(ValidationError)
    def invalid_contract(error):
        fields = [".".join(str(part) for part in item["loc"]) for item in error.errors()]
        return jsonify(error="Check these fields: " + ", ".join(fields)), 422

    @blueprint.errorhandler(ValueError)
    def invalid_input(error):
        return jsonify(error=str(error)), 400

    @blueprint.errorhandler(DraftConflict)
    def conflict(error):
        return jsonify(error=str(error)), 409

    @blueprint.errorhandler(KeyError)
    def not_found(error):
        return jsonify(error="Assessment draft not found."), 404

    @blueprint.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return jsonify(error="The combined PDF upload must not exceed 24 MiB."), 413

    @blueprint.errorhandler(APIError)
    def api_failure(error):
        current_app.logger.warning("Assessment API failed: %s", type(error).__name__)
        return jsonify(error="The assessment API is unavailable or rejected the report. Check configuration and try again."), 502

    @blueprint.errorhandler(ImportServiceError)
    def incomplete_result(error):
        return jsonify(error=str(error)), 502

    @blueprint.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return blueprint
