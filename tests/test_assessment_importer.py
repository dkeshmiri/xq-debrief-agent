import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from flask import Flask
from pydantic import ValidationError
from assessment_drafts import DraftStore
from assessment_importer import AssessmentImporter, ImportServiceError
from assessment_routes import create_assessment_blueprint
from assessment_schema import Evidence, Extraction, Facts, FamilyLanguage, missing_fields, validate_review
from schemas import validate_persona

BASE = Path(__file__).resolve().parent.parent


def fixtures():
    persona = json.loads((BASE / "data/personas/samuel.json").read_text())
    facts = {key: copy.deepcopy(persona[key]) for key in ("person", "assessment", "disc", "driving_forces", "eq")}
    for key in ("person_id", "family_role"):
        facts["person"].pop(key)
    facts["assessment"].pop("assessment_id")
    disc = {key: facts["disc"].pop(key) for key in ("behavioral_characteristics", "value_to_family", "communication_do", "communication_dont")}
    forces = {key: facts["driving_forces"].pop(key) for key in ("motivational_strengths", "energizers", "stressors")}
    return (Extraction(facts=Facts.model_validate(facts), evidence=[], sections=[], warnings=[]),
            FamilyLanguage(disc=disc, driving_forces=forces, integrated=persona["integrated"]))


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.extraction, self.language = fixtures()
        self.client = Mock()
        self.service = AssessmentImporter(client=self.client, model="test-model")

    def reply(self, value):
        self.client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=value)

    def test_entire_pdf_is_sent_with_chart_images_and_no_response_storage(self):
        self.reply(self.extraction)
        self.service.extract([("report.pdf", b"%PDF-1.7\ncomplete report")])
        args = self.client.responses.parse.call_args.kwargs
        file = args["input"][0]["content"][0]
        self.assertEqual(file["detail"], "high")
        self.assertTrue(file["file_data"].startswith("data:application/pdf;base64,"))
        self.assertFalse(args["store"])
        self.assertIn("untrusted source DATA", args["instructions"])
        self.assertEqual(args["model"], "test-model")

    def test_single_document_citations_use_actual_upload_name(self):
        self.extraction.evidence = [Evidence(field="disc.natural.D", document="not supplied", page=24, observation="D 72")]
        self.extraction.warnings = ["Filename not supplied.", "Age is unknown."]
        self.reply(self.extraction)
        result = self.service.extract([("actual-report.pdf", b"%PDF-1.7")])
        self.assertEqual(result.evidence[0].document, "actual-report.pdf")
        self.assertEqual(result.warnings, ["Age is unknown."])
        self.assertIn("actual-report.pdf", self.client.responses.parse.call_args.kwargs["input"][0]["content"][-1]["text"])

    def test_bad_pdf_and_file_counts_rejected_before_api(self):
        for reports in ([], [("x.pdf", b"bad")], [("x.exe", b"%PDF-")], [("x.pdf", b"%PDF-")] * 4):
            with self.subTest(reports=reports), self.assertRaises(ValueError):
                self.service.extract(reports)
        self.client.responses.parse.assert_not_called()

    def test_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):
            self.service.extract([("x.pdf", b"%PDF-"), ("x.pdf", b"%PDF-")])

    def test_partial_or_refused_response_rejected(self):
        for status, parsed in (("incomplete", self.extraction), ("completed", None)):
            self.client.responses.parse.return_value = SimpleNamespace(status=status, output_parsed=parsed)
            with self.assertRaises(ImportServiceError):
                self.service.extract([("x.pdf", b"%PDF-")])

    def test_all_reviewed_facts_and_operator_role_are_preserved(self):
        self.extraction.facts.disc.natural.D = 93
        self.reply(self.language)
        result = self.service.generate(self.extraction, "Grandparent")
        persona = result["persona"]
        validate_persona(persona)
        self.assertTrue(result["ready_for_debrief"])
        self.assertEqual(persona["person"]["family_role"], "Grandparent")
        for key in ("disc", "driving_forces", "eq"):
            for field, value in self.extraction.facts.model_dump()[key].items():
                self.assertEqual(persona[key][field], value)
        self.assertEqual(set(persona), {"schema_version", "person", "assessment", "disc", "driving_forces", "eq", "integrated"})
        self.assertNotEqual(persona["person"]["person_id"], "samuel_demo_001")

    def test_missing_eq_is_explicit_draft_not_invented_data(self):
        self.extraction.facts.eq.scores.self_awareness = None
        self.reply(self.language)
        result = self.service.generate(self.extraction, "Sibling")
        self.assertFalse(result["ready_for_debrief"])
        self.assertIn("eq.scores.self_awareness", result["missing_fields"])
        self.assertIsNone(result["persona"]["eq"]["scores"]["self_awareness"])

    def test_age_optional_zero_is_valid(self):
        self.extraction.facts.person.age = None
        self.extraction.facts.disc.natural.D = 0
        self.reply(self.language)
        result = self.service.generate(self.extraction, "Sibling")
        self.assertTrue(result["ready_for_debrief"])
        self.assertNotIn("age", result["persona"]["person"])
        self.assertEqual(result["persona"]["disc"]["natural"]["D"], 0)

    def test_bad_numeric_values_rejected(self):
        for value in (-1, 101, True, "72", float("nan"), float("inf")):
            data = self.extraction.model_dump()
            data["facts"]["disc"]["natural"]["D"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Extraction.model_validate(data)

    def test_duplicate_clusters_and_non_iso_date_rejected(self):
        self.extraction.facts.driving_forces.primary_cluster.append("Resourceful")
        with self.assertRaises(ValueError): validate_review(self.extraction.facts)
        self.extraction.facts.driving_forces.primary_cluster.pop()
        self.extraction.facts.assessment.assessment_date = "12/3/2025"
        with self.assertRaises(ValueError): validate_review(self.extraction.facts)
        self.extraction.facts.assessment.assessment_date = None
        self.assertIn("assessment.assessment_date", missing_fields(self.extraction.facts))

    def test_language_cannot_override_score_fields(self):
        data = self.language.model_dump()
        data["disc"]["natural"] = {"D": 10}
        with self.assertRaises(ValidationError): FamilyLanguage.model_validate(data)


class ImportRoutesTests(unittest.TestCase):
    def setUp(self):
        self.extraction, self.language = fixtures()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = DraftStore(self.directory.name)
        self.draft = self.store.create(self.extraction, "Parent")
        self.service = Mock()
        self.service.extract.return_value = self.extraction
        self.service.generate.return_value = {"persona": {}, "ready_for_debrief": True, "missing_fields": []}
        self.app = Flask(__name__, template_folder=str(BASE / "templates"))
        self.app.config.update(TESTING=True, MAX_CONTENT_LENGTH=25 * 1024 * 1024)
        self.app.register_blueprint(create_assessment_blueprint(self.service, self.store))
        self.http = self.app.test_client()

    def payload(self, pin="2020", revision=1):
        facts = self.extraction.facts.model_dump()
        facts["eq"]["scores"]["motivation"] = 44
        return {"revision": revision, "facts": facts, "family_role": "Grandparent", "pin": pin}

    def save(self, **kwargs):
        return self.http.post(f'/api/assessments/{self.draft["id"]}/override', json=self.payload(**kwargs))

    def test_page_and_private_response(self):
        response = self.http.get("/json-maker")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Override PIN", response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_wrong_pin_cannot_save(self):
        response = self.save(pin="0000")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.store.get(self.draft["id"]), self.draft)

    def test_correct_pin_saves_and_survives_new_store_instance(self):
        response = self.save()
        self.assertEqual(response.status_code, 200)
        saved = DraftStore(self.directory.name).get(self.draft["id"])
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(saved["extraction"]["facts"]["eq"]["scores"]["motivation"], 44)
        self.assertEqual(saved["family_role"], "Grandparent")
        self.assertEqual(len(saved["overrides"][0]["changes"]), 2)
        self.assertNotIn('"pin"', json.dumps(saved))
        self.assertEqual(self.http.get(f'/api/assessments/{self.draft["id"]}').json["revision"], 2)

    def test_no_pin_or_invalid_values_cannot_save(self):
        payload = self.payload()
        payload.pop("pin")
        self.assertEqual(self.http.post(f'/api/assessments/{self.draft["id"]}/override', json=payload).status_code, 422)
        payload = self.payload()
        payload["facts"]["eq"]["scores"]["motivation"] = 999
        self.assertEqual(self.http.post(f'/api/assessments/{self.draft["id"]}/override', json=payload).status_code, 422)
        self.assertEqual(self.store.get(self.draft["id"])["revision"], 1)

    def test_stale_revision_cannot_overwrite_saved_scores(self):
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(self.save().status_code, 409)

    def test_generation_uses_saved_override_not_browser_facts(self):
        self.save()
        payload = {"draft_id": self.draft["id"], "revision": 2, "reviewed": True}
        response = self.http.post("/api/assessments/generate", json=payload)
        self.assertEqual(response.status_code, 200)
        facts, role = self.service.generate.call_args.args
        self.assertEqual(facts.facts.eq.scores.motivation, 44)
        self.assertEqual(role, "Grandparent")
        payload["extraction"] = self.extraction.model_dump()
        self.assertEqual(self.http.post("/api/assessments/generate", json=payload).status_code, 422)

    def test_generation_rejects_unreviewed_and_stale_drafts(self):
        payload = {"draft_id": self.draft["id"], "revision": 1, "reviewed": False}
        self.assertEqual(self.http.post("/api/assessments/generate", json=payload).status_code, 422)
        payload.update(reviewed=True, revision=10)
        self.assertEqual(self.http.post("/api/assessments/generate", json=payload).status_code, 409)
        self.service.generate.assert_not_called()

    def test_extract_requires_role_and_accepts_multiple_reports(self):
        response = self.http.post("/api/assessments/extract", data={"reports": (io.BytesIO(b"%PDF-"), "x.pdf")})
        self.assertEqual(response.status_code, 400)
        response = self.http.post("/api/assessments/extract", data={"family_role": "Mother", "reports": [(io.BytesIO(b"%PDF-1"), "first.pdf"), (io.BytesIO(b"%PDF-2"), "eq.pdf")]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.service.extract.call_args.args[0]), 2)
        self.assertEqual(response.json["family_role"], "Mother")
        self.assertEqual(self.store.get(response.json["draft_id"])["revision"], 1)

    def test_upload_limit_is_json_error(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 10
        response = self.http.post("/api/assessments/extract", data={"family_role": "Parent", "reports": (io.BytesIO(b"%PDF-1"), "x.pdf")})
        self.assertEqual(response.status_code, 413)
        self.assertIn("error", response.json)

    def test_path_traversal_and_unknown_drafts_rejected(self):
        with self.assertRaises(KeyError): self.store.get("../../.env")
        self.assertEqual(self.http.get("/api/assessments/not-a-uuid").status_code, 404)

    def test_review_changing_during_generation_rejected(self):
        def generate(*args):
            self.store.override(self.draft["id"], 1, self.extraction.facts, "Sibling")
            return {"persona": {}}
        self.service.generate.side_effect = generate
        response = self.http.post("/api/assessments/generate", json={"draft_id": self.draft["id"], "revision": 1, "reviewed": True})
        self.assertEqual(response.status_code, 409)
