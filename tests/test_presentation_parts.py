"""Part handoffs use separate rooms without overlapping speech or retrying work."""
import copy
import threading
import unittest
from unittest.mock import Mock
from flask import Flask
from presentation import Presentation, create_presentation_blueprint
from presentation_bundle import bundle_presentation


class Provider:
    pal_id = 'test'
    conversation_id = None
    connected = False
    pal_participant_ids = set()

    def __init__(self):
        self.calls = []
        self.counter = 0
        self.fail_end = self.fail_start = False

    def create_conversation(self, **options):
        self.calls.append(('create', options))
        if self.fail_start:
            raise RuntimeError('join failed')
        assert self.conversation_id is None, 'old room still open'
        self.counter += 1
        self.conversation_id = f'room-{self.counter}'
        self.connected = True
        return dict(conversation_id=self.conversation_id, conversation_url='https://test.invalid/room')

    def end_conversation(self):
        self.calls.append(('end', self.conversation_id))
        if self.fail_end:
            raise RuntimeError('end failed')
        self.on_system_event({'conversation_id':self.conversation_id,
                              'properties':{'shutdown_reason':'ended'}})
        self.conversation_id = None
        self.connected = False

    def speak(self, text):
        self.calls.append(('speak',text))


class PresentationPartsTests(unittest.TestCase):
    def setUp(self):
        self.provider = Provider()
        self.now = 0
        self.session = Presentation(self.provider, clock=lambda:self.now)
        self.bundle = dict(presentation_version=1, profile=dict(source='Test', disc={}),
            chapters=[dict(title=str(i),text='Exact text '+str(i),visual='disc_di') for i in range(3)],
            parts=[dict(title='First',chapter_start=0,chapter_end=0),
                   dict(title='Second',chapter_start=1,chapter_end=2)])
        self.session.configure(self.bundle)

    def complete(self, inference='first'):
        for kind in ('started_speaking','stopped_speaking'):
            self.session.on_playback(dict(event_type='conversation.replica.'+kind,
                inference_id=inference,conversation_id=self.provider.conversation_id,
                properties=dict(interrupted=False)))

    def ready_for_handoff(self):
        self.session.start()
        self.session.play('play')
        self.complete()

    def test_end_then_create_new_capped_room_without_sending_echo(self):
        self.ready_for_handoff()
        self.now = 800
        with self.assertRaises(ValueError):
            self.session.play('next')
        result = self.session.next_part('room-1')
        self.assertEqual(result['conversation_id'], 'room-2')
        self.assertEqual([c[0] for c in self.provider.calls], ['create','speak','end','create'])
        self.assertTrue(all(c[1]['max_call_duration'] == 900 for c in self.provider.calls if c[0]=='create'))
        state = self.session.status()
        self.assertEqual((state['part_index'],state['index'],state['remaining_seconds']), (1,1,900))
        self.assertFalse(state['pending'])
        self.assertIsNone(state['shutdown_reason'])
        self.session.play('play')
        self.assertEqual(self.provider.calls[-1], ('speak','Exact text 1'))

    def test_duplicate_or_stale_handoff_cannot_skip_or_create_another_room(self):
        self.ready_for_handoff()
        self.session.next_part('room-1')
        for session_id in ('room-1','room-2',None):
            with self.assertRaises(ValueError):
                self.session.next_part(session_id)
        self.assertEqual(self.provider.counter,2)

    def test_pending_and_interrupted_narration_cannot_advance(self):
        self.session.start()
        self.session.play('play')
        with self.assertRaises(ValueError):
            self.session.next_part('room-1')
        self.session.on_playback(dict(event_type='conversation.replica.started_speaking',inference_id='x'))
        self.session.on_playback(dict(event_type='conversation.replica.stopped_speaking',inference_id='x',properties={'interrupted':True}))
        with self.assertRaises(ValueError):
            self.session.next_part('room-1')
        self.assertEqual(self.provider.counter,1)

    def test_old_events_cannot_own_next_parts_pending_speech(self):
        self.ready_for_handoff()
        self.session.next_part('room-1')
        self.session.play('play')
        for kind in ('started_speaking','stopped_speaking'):
            for event in (dict(conversation_id='room-1',inference_id='late-unknown'),dict(inference_id='first')):
                self.session.on_playback(dict(event_type='conversation.replica.'+kind,**event))
        self.assertIsNone(self.session.tracker.inference_id)
        self.assertFalse(self.session.completed)
        self.assertIsNotNone(self.session.tracker.utterance_id)

    def test_failed_end_never_opens_new_room_and_failed_start_never_speaks(self):
        for failure in ('fail_end','fail_start'):
            self.setUp()
            self.ready_for_handoff()
            setattr(self.provider,failure,True)
            with self.assertRaises(RuntimeError):
                self.session.next_part('room-1')
            self.assertEqual(self.session.shutdown_reason,'part_transition_failed')
            self.assertFalse(self.session.busy)
            self.assertEqual(sum(c[0]=='speak' for c in self.provider.calls),1)
            with self.assertRaises(ValueError):
                self.session.next_part(self.provider.conversation_id)
            if failure == 'fail_end':
                self.assertEqual(sum(c[0]=='create' for c in self.provider.calls),1)

    def test_network_handoff_releases_lock_and_concurrent_requests_are_rejected(self):
        self.ready_for_handoff()
        entered, release = threading.Event(), threading.Event()
        original = self.provider.end_conversation
        def end():
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test timed out')
            original()
        self.provider.end_conversation = end
        thread = threading.Thread(target=lambda:self.session.next_part('room-1'))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(self.session.lock.acquire(timeout=.5))
            self.session.lock.release()
            with self.assertRaises(ValueError):
                self.session.next_part('room-1')
            with self.assertRaises(ValueError):
                self.session.configure(self.bundle)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.provider.counter,2)

    def test_restart_returns_to_first_part_and_single_part_has_no_handoff(self):
        self.ready_for_handoff()
        self.session.next_part('room-1')
        self.session.end()
        self.session.start()
        self.assertEqual((self.session.part_index,self.session.index),(0,0))
        self.session.end()
        one = copy.deepcopy(self.bundle)
        del one['parts']
        self.session.configure(one)
        self.assertEqual(self.session.status()['part_count'],1)

    def test_invalid_parts_are_rejected_atomically(self):
        for parts in ([],{},[dict(title='Gap',chapter_start=1,chapter_end=2)],
                      [dict(title='Overlap',chapter_start=0,chapter_end=1),dict(title='B',chapter_start=1,chapter_end=2)],
                      [dict(title='Missing',chapter_start=0,chapter_end=1)],
                      [dict(title='Bool',chapter_start=False,chapter_end=2)]):
            bad = copy.deepcopy(self.bundle)
            bad['parts'] = parts
            before = self.session.chapters
            with self.assertRaises(ValueError):
                self.session.configure(bad)
            self.assertEqual(self.session.chapters,before)

    def test_handoff_route_requires_operator_and_current_session(self):
        app = Flask(__name__)
        app.register_blueprint(create_presentation_blueprint(self.session))
        api = app.test_client()
        self.assertEqual(api.post('/api/presentation/next-part',json={'session_id':'room-1'}).status_code,403)
        api.post('/api/presentation/unlock',json={'pin':'2020'})
        self.ready_for_handoff()
        self.assertEqual(api.post('/api/presentation/next-part',json={}).status_code,409)
        self.assertEqual(api.post('/api/presentation/next-part',json={'session_id':'room-1'}).status_code,200)
        self.assertEqual(api.post('/api/presentation/next-part',json={'session_id':'room-1'}).status_code,409)


if __name__ == '__main__':
    unittest.main()
