import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from family_repository import FamilyRepository
from playback_latency import PlaybackLatency


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        data = copy.deepcopy(app_module.repository.family_data)
        for member in data["members"]:
            member["persona_file"] = str(Path(member["persona_file"]).resolve())
        self.manifest = self.root / "family.json"
        self.manifest.write_text(json.dumps(data))
        self.repository = FamilyRepository(self.manifest)
        self.persona = copy.deepcopy(self.repository.get_default_persona())
        self.persona["person"]["person_id"] = "new-person"
        self.persona["person"]["display_name"] = "New Person"

    def test_saved_profile_is_selectable_and_survives_reload(self):
        directory = self.root / "personas"
        filename = self.repository.save_persona(self.persona, directory)
        self.assertEqual(self.repository.save_persona(self.persona, directory), filename)
        reloaded = FamilyRepository(self.manifest)
        reloaded.set_active_person("new-person")
        self.assertEqual(reloaded.get_active_persona(), self.persona)
        with (patch.object(app_module, "repository", reloaded),
              patch.object(app_module, "engine", app_module.engine),
              patch.object(app_module, "orchestrator", app_module.orchestrator),
              patch.object(app_module, "playback_tracker", app_module.playback_tracker),
              patch.object(app_module, "answer_playback_tracker", app_module.answer_playback_tracker),
              patch.object(app_module, "active_tavus_conversation_id", None),
              patch.object(app_module, "session_starting", False),
              patch.object(app_module, "session_ending", False)):
            client = app_module.app.test_client()
            self.assertIn(filename, [p["file"] for p in client.get("/api/personas").json["personas"]])
            response = client.post("/api/person/select", json={"file": filename})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["selected_person"], "New Person")

    def test_failed_manifest_write_does_not_publish_profile(self):
        original = self.manifest.read_text()
        with patch.object(Path, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.repository.save_persona(self.persona, self.root / "personas")
        self.assertFalse(self.repository.has_person("new-person"))
        self.assertEqual(self.manifest.read_text(), original)
        self.assertEqual(list((self.root / "personas").glob("*.json")), [])

    def test_invalid_profile_and_id_collision_rejected(self):
        self.persona["eq"]["total_eq"] = None
        with self.assertRaises(ValueError):
            self.repository.save_persona(self.persona, self.root / "personas")
        self.persona = copy.deepcopy(self.repository.get_default_persona())
        self.persona["person"]["display_name"] = "Changed"
        with self.assertRaises(ValueError):
            self.repository.save_persona(self.persona, self.root / "personas")

    def test_menu_and_console_are_separate(self):
        client = app_module.app.test_client()
        self.assertIn(b"Use a saved profile", client.get("/").data)
        self.assertIn(b"Create a new profile", client.get("/").data)
        self.assertIn(b"video-container", client.get("/debrief").data)

    def test_adding_profile_during_session_is_rejected(self):
        with patch.object(app_module, "active_tavus_conversation_id", "active-session"):
            with self.assertRaises(app_module.DraftConflict):
                app_module.save_assessment_persona(self.persona)


class LatencyTests(unittest.TestCase):
    def test_timings_separate_local_and_provider_wait_and_ignore_stale_events(self):
        now = [10.0]
        timing = PlaybackLatency(lambda: now[0])
        timing.submitted(4, stopped_at=9.98, handler_entered_at=9.99)
        now[0] = 10.002
        timing.sent(4)
        timing.started(3)
        self.assertTrue(timing.snapshot()["pending"])
        now[0] = 10.7
        timing.started(4)
        timing.started(4)
        self.assertEqual(len(timing.samples), 1)
        self.assertEqual(timing.samples[0]["stop_event_to_submit_ms"], 20)
        self.assertEqual(timing.samples[0]["submit_to_start_event_ms"], 700)
        self.assertEqual(timing.samples[0]["send_call_ms"], 2)
        self.assertEqual(timing.samples[0]["lock_wait_ms"], 10)

    def test_reset_discards_pending_and_history_is_bounded(self):
        timing = PlaybackLatency(lambda: 1)
        timing.submitted(1)
        timing.reset_pending()
        timing.started(1)
        self.assertEqual(len(timing.samples), 0)
        for i in range(110):
            timing.submitted(i)
            timing.started(i)
        self.assertEqual(len(timing.samples), 100)
