"""Explicit live diagnostic. Creates one short paid Tavus session, then ends it."""
import os
import threading
import time
from tavus_client import TavusClient


def tavus_check():
    client = TavusClient()
    client.pal_id = os.getenv('XQ_PRESENTATION_TAVUS_PAL_ID') or client.pal_id
    started, stopped = threading.Event(), threading.Event()
    inference = [None]
    def event(message):
        if message.get('event_type') == 'conversation.replica.started_speaking':
            inference[0] = message.get('inference_id')
            started.set()
        elif (message.get('event_type') == 'conversation.replica.stopped_speaking'
              and message.get('inference_id') == inference[0] and inference[0]):
            stopped.set()
    client.on_playback_event = event
    try:
        client.create_conversation(conversation_name='XQ Windows transport verification', max_call_duration=120)
        print('Tavus room created; Windows browser joined.', flush=True)
        deadline = time.monotonic() + 45
        while not client.connected and time.monotonic() < deadline:
            time.sleep(.1)
        if not client.connected:
            raise RuntimeError('Windows browser did not confirm the Daily connection.')
        # Match the app's startup grace period rather than sending during join.
        time.sleep(5)
        client.speak('Hello. Welcome to XQ. This is a short Windows connection check.')
        if not started.wait(40):
            raise RuntimeError('Tavus did not report canonical speech start.')
        print('Canonical speech start received.', flush=True)
        if not stopped.wait(40):
            raise RuntimeError('Tavus did not report matching speech stop.')
        print('Matching canonical speech stop received. Native Windows Tavus check passed.', flush=True)
    finally:
        try:
            if client.conversation_id:
                client.end_conversation()
                print('Diagnostic Tavus session ended.', flush=True)
        finally:
            client.disconnect()
