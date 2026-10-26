import copy
import json
import logging
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from unittest.mock import patch

from family_repository import FamilyRepository
from playback_logging import NonblockingQueueHandler
from logging.handlers import QueueListener

ROOT = Path(__file__).resolve().parents[1]

class PortabilityTests(unittest.TestCase):
    def test_roster_loads_without_using_working_directory(self):
        with patch('pathlib.Path.cwd', side_effect=AssertionError('CWD must not be used')):
            repo = FamilyRepository('data/families/demo_family.json')
        self.assertTrue(repo.has_person('samuel_demo_001'))

    def test_saved_profile_moves_with_project_and_reloads(self):
        persona = FamilyRepository(ROOT / 'data/families/demo_family.json').get_default_persona()
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = base / 'original'
            original.mkdir()
            manifest = original / 'roster.json'
            data = json.loads((ROOT / 'data/families/demo_family.json').read_text())
            data['members'] = [data['members'][0]]
            (original / 'data/personas').mkdir(parents=True)
            (original / data['members'][0]['persona_file']).write_text(json.dumps(persona))
            manifest.write_text(json.dumps(data))
            with patch('family_repository.PROJECT_ROOT', original):
                repo = FamilyRepository(manifest)
                new = copy.deepcopy(persona)
                new['person']['person_id'] = 'portable'
                name = repo.save_persona(new, Path('data/personas'))
                self.assertEqual(repo.get_member('portable')['persona_file'], 'data/personas/'+name)
            moved = base / 'moved'
            original.rename(moved)
            with patch('family_repository.PROJECT_ROOT', moved):
                reloaded = FamilyRepository(moved / 'roster.json')
                self.assertEqual(reloaded.get_persona('portable'), new)

class PlaybackLoggingTests(unittest.TestCase):
    def test_slow_output_does_not_block_producer(self):
        entered, release, returned = Event(), Event(), Event()
        class BlockedOutput(logging.Handler):
            def emit(self, record):
                entered.set()
                release.wait(3)
        queue = Queue(maxsize=2)
        handler = NonblockingQueueHandler(queue)
        listener = QueueListener(queue, BlockedOutput())
        listener.start()
        record = logging.LogRecord('test', logging.WARNING, '', 0, 'Diagnostic', (), None)
        def produce():
            handler.handle(record)
            returned.set()
        worker = Thread(target=produce, daemon=True)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(returned.wait(.5), 'Playback producer waited for log output')
            # Filling the bounded queue must not block or write logging errors.
            with patch('sys.stderr.write', side_effect=AssertionError('Synchronous output')):
                for _ in range(10):
                    handler.handle(record)
        finally:
            release.set()
            worker.join(2)
            queue.join()
            listener.stop()

