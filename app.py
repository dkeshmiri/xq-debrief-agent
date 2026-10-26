from playback_logging import logger
import json
import os
import math
from pathlib import Path
import time
import traceback
from copy import deepcopy
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
)

from assessment_routes import create_assessment_blueprint
from assessment_drafts import DraftConflict
from debrief_engine import DebriefEngine
from debrief_state import DebriefState
from family_repository import FamilyRepository
from workspace_experience import Experience
from family_routes import FamilySelectionError, create_family_blueprint
from tavus_client import TavusClient
from conversation_orchestrator import ConversationOrchestrator, ConversationPhase
from playback_event_tracker import PlaybackEventTracker
from sentence_splitter import split_sentences
from threading import Event, RLock, Thread
from playback_coordinator import PlaybackCoordinator
from playback_latency import PlaybackLatency
from activity_presenter import describe_activity
from failure_recovery import FailureRecovery, RecoveryState
from recovery_controller import RecoveryController
from daily import Daily
from speech_transcriber import (
    AUDIO_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    SpeechTranscriber,
)
from voice_activity import (
    EnergySpeechScorer,
    SegmenterConfig,
)
from voice_input import VoiceInputPipeline
from voice_intent import (
    VoiceIntent,
    classify_question_mode_utterance,
)


# =========================================================
# ENVIRONMENT
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
EXPERIENCE = Experience(globals().get('WORKSPACE_EXPERIENCE', 'family'))
WORKSPACE_DATA = Path(globals().get('WORKSPACE_DATA_ROOT') or os.getenv('XQ_BUSINESS_DATA_DIR') or BASE_DIR / 'data/business')

load_dotenv(
    BASE_DIR / ".env"
)


# =========================================================
# APPLICATION CONFIG
# =========================================================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.register_blueprint(create_assessment_blueprint(experience=EXPERIENCE.name))
if EXPERIENCE.business:
    app.config['ASSESSMENT_DRAFT_DIR'] = WORKSPACE_DATA / 'assessment_drafts'

FAMILY_MANIFEST_PATH = (
    BASE_DIR
    / "data"
    / "families"
    / "demo_family.json"
)

PERSONA_DIR = (
    BASE_DIR
    / "data"
    / "personas"
)


# =========================================================
# XQ ENGINE SETUP
# =========================================================

if EXPERIENCE.business:
    from business_repository import BusinessRepository
    repository = BusinessRepository(WORKSPACE_DATA / 'roster.json')
    PERSONA_DIR = WORKSPACE_DATA / 'personas'
else:
    repository = FamilyRepository(str(FAMILY_MANIFEST_PATH))


def create_engine_for_active_person() -> DebriefEngine:
    if EXPERIENCE.business and repository.active_person_id is None:
        from business_repository import UnselectedEngine
        return UnselectedEngine()
    member = repository.get_active_member()
    if EXPERIENCE.business:
        return DebriefEngine(BASE_DIR / member['persona_file'], experience='business')
    return DebriefEngine(
        BASE_DIR / member["persona_file"]
    )


engine = create_engine_for_active_person()
orchestrator = ConversationOrchestrator(engine)

playback_tracker = PlaybackEventTracker()
answer_playback_tracker = PlaybackEventTracker()
playback_lock = RLock()
playback_latency = PlaybackLatency()
reasoning_active = Event()


untracked_playback_active = False
interruption_pending = False
interrupted_inference_id = None
# Keep known old turns across resets: delayed events must not bind to new Echo.
retired_inference_ids = set()
untracked_inference_id = None
session_ending = False

failure_recovery = FailureRecovery()
recovery_controller = RecoveryController(
    failure_recovery
)

# Voice barge-in that arrived between sentences, before
# Tavus reported the next sentence's inference ID.
voice_interrupt_requested_at: float | None = None
last_voice_event: dict | None = None

VOICE_INTERRUPT_REQUEST_TTL_SECONDS = 3.0
VOICE_QUESTION_WAIT_SECONDS = 4.0

# Question mode closes by itself after this many seconds
# without a question, a dismissal or user speech.
# 0 disables the timeout.
QUESTION_MODE_TIMEOUT_SECONDS = float(
    os.getenv("XQ_QUESTION_TIMEOUT_SECONDS", "30")
)
QUESTION_TIMEOUT_POLL_SECONDS = 0.25

if not math.isfinite(QUESTION_MODE_TIMEOUT_SECONDS) or QUESTION_MODE_TIMEOUT_SECONDS < 0:
    raise RuntimeError(
        "XQ_QUESTION_TIMEOUT_SECONDS must be finite and non-negative."
    )

question_mode_deadline: float | None = None
voice_session_generation = 0
http_voice_pending = False
question_mode_generation = 0
background_stop = Event()


class RouteError(Exception):
    """
    A playback-state conflict, reported to HTTP callers
    as an error response and to voice input as a log line.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 409,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code

# =========================================================
# TAVUS SETUP
# =========================================================

from local_playback import LocalPlayback, local_playback_blueprint

LOCAL_PLAYBACK = os.getenv('XQ_PLAYBACK_PROVIDER', 'kokoro') == 'kokoro'
# Retain this legacy transport name while the orchestration contract stays shared.
tavus = LocalPlayback() if LOCAL_PLAYBACK else TavusClient()
if LOCAL_PLAYBACK:
    app.register_blueprint(local_playback_blueprint(tavus))

@app.context_processor
def playback_template_settings():
    return {'local_playback': LOCAL_PLAYBACK}
if EXPERIENCE.business:
    tavus.voice_user_name = os.getenv('XQ_BUSINESS_VOICE_USER_NAME', 'XQ Workplace Participant')
    tavus.pal_id = os.getenv('XQ_BUSINESS_TAVUS_PAL_ID') or tavus.pal_id


def handle_tavus_playback_event(event: dict) -> None:
    """
    Update XQ playback state from Tavus events.

    Tracked narration advances only after a matching
    non-interrupted completion event.
    """

    global untracked_playback_active
    global interruption_pending
    global interrupted_inference_id
    global untracked_inference_id, question_mode_generation

    received_at = time.monotonic()
    with playback_lock:
        handler_entered_at = time.monotonic()
        event_type = event.get("event_type")
        inference_id = event.get("inference_id")
        if session_ending:
            return
        if event_type not in (PlaybackEventTracker.STARTED, PlaybackEventTracker.STOPPED):
            return
        if not isinstance(inference_id, str) or not inference_id:
            return
        if inference_id in retired_inference_ids:
            return
        conversation_id = event.get("conversation_id")
        if conversation_id and conversation_id != active_tavus_conversation_id:
            return

        # Handle deliberate interruptions before
        # normal narration completion.

        if interruption_pending:
            inference_id = event.get("inference_id")

            if (
                event_type
                == "conversation.replica.stopped_speaking"
                and inference_id == interrupted_inference_id
            ):
                logger.debug('%s', "[XQ INTERRUPT] Tavus confirmed "
                    "that narration has stopped.")

                orchestrator.interrupt()
                question_mode_generation += 1
                retired_inference_ids.add(inference_id)
                playback_tracker.cancel()
                restart_question_mode_timer()

                interruption_pending = False
                interrupted_inference_id = None

                logger.debug('%s', "[XQ INTERRUPT] Narration paused. "
                    f"Preserved sentence index: "
                    f"{orchestrator.cursor.sentence_index}")

            return

        if answer_playback_tracker.utterance_id is not None:
            completed = answer_playback_tracker.handle_event(
                event
            )

            if completed is not None:
                retired_inference_ids.add(
                    inference_id
                )

                turn = orchestrator.answer_finished()

                if turn is not None:
                    PlaybackCoordinator(
                        orchestrator,
                        playback_tracker,
                    ).register_utterance(
                        turn.utterance_id
                    )

                    try:
                        speak_text(
                            turn.text
                        )

                    except Exception as error:
                        recovery_controller.handle_resume_submission_error(
                            orchestrator=orchestrator,
                            narration_tracker=playback_tracker,
                        )
                        
                        logger.warning('%s', "[XQ RECOVERY] "
                            "Resume submission uncertain. "
                            "Narration ownership preserved: "
                            f"{error}")

            elif (
                event_type
                == PlaybackEventTracker.STOPPED
                and answer_playback_tracker.utterance_id
                is None
            ):
                retired_inference_ids.add(
                    inference_id
                )

                recovery_controller.handle_answer_interrupted(
                    orchestrator=orchestrator,
                    answer_tracker=answer_playback_tracker,
                )

                logger.debug('%s', "[XQ RECOVERY] "
                    "Interrupted answer recovered. "
                    "Narration position preserved.")

            return

        if playback_tracker.utterance_id is None:
            if event_type == PlaybackEventTracker.STARTED:
                if untracked_inference_id is None:
                    untracked_inference_id = inference_id
                    untracked_playback_active = True
            elif inference_id == untracked_inference_id:
                retired_inference_ids.add(inference_id)
                untracked_inference_id = None
                untracked_playback_active = False
            return

        coordinator = PlaybackCoordinator(
            orchestrator=orchestrator,
            tracker=playback_tracker,
        )

        completed = coordinator.handle_playback_event(
            event
        )
        if event_type == PlaybackEventTracker.STARTED and playback_tracker.inference_id == inference_id:
            playback_latency.started(playback_tracker.utterance_id)

        if (
            event_type == PlaybackEventTracker.STARTED
            and failure_recovery.state
            == RecoveryState.RESUME_DELIVERY_UNCERTAIN
            and playback_tracker.inference_id == inference_id
        ):
            # The resume that raised was delivered after all.
            # Normal tracking takes over from here.
            recovery_controller.confirm_resume_started(
                inference_id=inference_id,
            )
            recovery_controller.reset()

            logger.warning('%s', "[XQ RECOVERY] Uncertain resume confirmed "
                f"by Tavus ({inference_id}). Recovery cleared.")

        if (
            event_type == PlaybackEventTracker.STARTED
            and voice_interrupt_requested_at is not None
        ):
            # The user started talking between sentences.
            # This sentence now has an inference ID: stop it.
            honour_voice_interrupt_request()
            return

        if completed:
            retired_inference_ids.add(inference_id)
            logger.debug('%s', "[XQ PLAYBACK] Sentence completed. "
                f"Next sentence index: "
                f"{orchestrator.cursor.sentence_index}")

            try:
                next_turn = submit_next_tracked_sentence(received_at, handler_entered_at)

            except Exception as error:
                logger.warning('%s', "[XQ PLAYBACK] Automatic continuation "
                    f"failed: {error}")
                return

            if next_turn is None:
                logger.debug('%s', "[XQ PLAYBACK] Current section finished.")

        elif event_type == (
            "conversation.replica.stopped_speaking"
        ):
            logger.debug('%s', "[XQ PLAYBACK] Stop event received; "
                "no sentence completion accepted.")


tavus.on_playback_event = handle_tavus_playback_event


# =========================================================
# VOICE INPUT SETUP
# =========================================================

def create_speech_scorer():
    """
    One speech detector per participant stream.

    XQ_VAD_BACKEND=daily  (default) Daily's native VAD
    XQ_VAD_BACKEND=energy loudness only, for testing
    """

    backend = os.getenv("XQ_VAD_BACKEND", "daily")

    if backend == "energy":
        return EnergySpeechScorer()

    if backend != "daily":
        raise RuntimeError(
            f"Unknown XQ_VAD_BACKEND: {backend!r}"
        )

    vad = Daily.create_native_vad(
        reset_period_ms=1000,
        sample_rate=VoiceInputPipeline.SAMPLE_RATE,
        channels=1,
    )

    return vad.analyze_frames


speech_transcriber = SpeechTranscriber()

active_tavus_conversation_id: str | None = None

session_ending = False
session_starting = False


# =========================================================
# HELPERS
# =========================================================

def get_available_personas() -> list[dict]:
    return [
        {"file": Path(member["persona_file"]).name,
         **{key: member[key] for key in ("person_id", "display_name", "family_role")}}
        for member in repository.list_members(debrief_enabled_only=True)
    ]

def error_response(
    message: str,
    status_code: int = 400,
):
    return jsonify({
        "ok": False,
        "error": message,
    }), status_code


def wait_for_tavus_connection(
    timeout_seconds: float = 10.0,
) -> bool:
    """
    Wait briefly for the backend Daily client
    to finish joining the Tavus room.
    """

    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    while (
        time.monotonic()
        < deadline
    ):
        if tavus.connected:
            return True

        time.sleep(0.1)

    return False


def current_payload() -> dict:
    member = repository.get_active_member() if repository.active_person_id is not None else {
        'person_id': '', 'display_name': 'No profile selected', 'family_role': ''}

    return {
    "active_person": {
        "person_id": (
            member["person_id"]
        ),
        "display_name": (
            member["display_name"]
        ),
        "family_role": (
            member["family_role"]
        ),
    },

    "state": (
        engine.get_current_state().value
    ),

    "content": (
        engine.get_current_content()
    ),

    "playback": {
        "phase": orchestrator.phase.value,
        "interruption_pending": interruption_pending,
        "answer_pending": answer_playback_tracker.utterance_id is not None,
        "section": (
            orchestrator.cursor.section.value
            if orchestrator.cursor.section is not None
            else None
        ),
        "sentence_index": (
            orchestrator.cursor.sentence_index
        ),
        "active_utterance_id": (
            orchestrator.cursor.active_utterance.id
            if orchestrator.cursor.active_utterance is not None
            else None
        ),
        "tracked_pending": (
            playback_tracker.utterance_id is not None
        ),
        "question_mode_timeout_seconds": (
            QUESTION_MODE_TIMEOUT_SECONDS or None
        ),
        "question_mode_seconds_left": (
            question_mode_seconds_left()
        ),
        "recovery_state": failure_recovery.state.value,
    },

    "tavus": tavus.status(),

    "voice": {
        **voice_pipeline.status(),
        "interrupt_requested": (
            voice_interrupt_requested_at is not None
        ),
        "last_event": last_voice_event,
    },
}


def speak_text(
    text: str,
) -> None:
    """
    Send already-approved XQ text to Tavus.
    """

    if not tavus.connected:
        raise RuntimeError(
            "The Tavus backend client "
            "is not connected."
        )

    global untracked_playback_active
    # Reserve untracked Echo before submission, including the pre-start gap.
    if playback_tracker.utterance_id is None and answer_playback_tracker.utterance_id is None:
        untracked_playback_active = True
    tavus.speak(text)
    if isinstance(tavus, LocalPlayback):
        cursor = orchestrator.cursor
        tavus.prefetch(cursor.sentences[cursor.sentence_index+1:cursor.sentence_index+3])


def play_section_text(text):
    if isinstance(tavus, LocalPlayback):
        orchestrator.load_current_section()
        submit_next_tracked_sentence()
    else:
        speak_text(text)


def tracked_playback_active() -> bool:
    """
    True while a tracked Tavus utterance is pending.
    """
    return playback_tracker.utterance_id is not None


def interruption_in_progress() -> bool:
    """
    True while waiting for Tavus to acknowledge
    a deliberate interruption.
    """
    return interruption_pending


def submit_next_tracked_sentence(stopped_at=None, handler_entered_at=None):
    """
    Submit the next sentence in the current section.

    Caller must already hold playback_lock.
    Returns the submitted SpeechTurn, or None if
    the current section has finished.
    """

    if interruption_pending:
        raise RuntimeError(
            "Cannot submit narration while "
            "an interruption is pending."
        )

    if playback_tracker.utterance_id is not None:
        raise RuntimeError(
            "A tracked sentence is already pending."
        )

    if answer_playback_tracker.utterance_id is not None or untracked_playback_active:
        raise RuntimeError(
            "Tavus is already speaking another response."
        )

    current_section = engine.get_current_state()

    if orchestrator.cursor.section != current_section:
        orchestrator.load_current_section()

    turn = orchestrator.next_narration()

    if turn is None:
        return None

    coordinator = PlaybackCoordinator(
        orchestrator=orchestrator,
        tracker=playback_tracker,
    )

    coordinator.register_utterance(
        turn.utterance_id
    )

    # If delivery raises, keep ownership because Echo may have been submitted.
    playback_latency.submitted(turn.utterance_id, stopped_at, handler_entered_at)
    speak_text(turn.text)
    playback_latency.sent(turn.utterance_id)

    logger.debug('Submitted utterance %s', turn.utterance_id)

    if (
        failure_recovery.state
        == RecoveryState.READY_TO_RESUME_NARRATION
    ):
        # Narration is back after an interrupted answer.
        recovery_controller.reset()

        logger.debug('%s', "[XQ RECOVERY] Narration resumed after an "
            "interrupted answer. Recovery cleared.")

    return turn

def serialized_route(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with playback_lock:
            if session_ending:
                return error_response("Session shutdown is in progress.", 409)
            return function(*args, **kwargs)
    return wrapped


def playback_route(function):
    @wraps(function)
    @serialized_route
    def wrapped(*args, **kwargs):
        if interruption_pending:
            return error_response("An interruption is pending. Wait for Tavus to stop speaking.", 409)
        if (playback_tracker.utterance_id is not None
                or answer_playback_tracker.utterance_id is not None
                or untracked_playback_active
                or orchestrator.phase == ConversationPhase.ANSWERING):
            return error_response("A playback utterance is already pending.", 409)
        if orchestrator.phase == ConversationPhase.QUESTION_READY and function.__name__ != "ask_question":
            return error_response("Narration is paused for a question.", 409)
        return function(*args, **kwargs)
    return wrapped


# =========================================================
# QUESTION MODE + VOICE HELPERS
# =========================================================

def reset_voice_state() -> None:
    """
    Caller must hold playback_lock.
    """

    global voice_interrupt_requested_at, question_mode_deadline
    global voice_session_generation, http_voice_pending, last_voice_event

    voice_session_generation += 1
    http_voice_pending = False
    voice_interrupt_requested_at = None
    question_mode_deadline = None
    last_voice_event = None
    voice_pipeline.reset()
    playback_latency.reset_pending()


def request_interruption() -> str:
    """
    Ask Tavus to stop the tracked sentence.

    Caller must hold playback_lock. Question mode opens
    when Tavus confirms the stop (see
    handle_tavus_playback_event).
    """

    global interruption_pending
    global interrupted_inference_id

    if interruption_pending:
        raise RouteError(
            "An interruption is already pending."
        )

    if not tracked_playback_active():
        raise RouteError(
            "There is no tracked narration to interrupt."
        )

    if playback_tracker.inference_id is None:
        raise RouteError(
            "Waiting for Tavus playback to start."
        )

    if not tavus.connected:
        raise RouteError(
            "Tavus is not connected."
        )

    interrupted_inference_id = (
        playback_tracker.inference_id
    )

    interruption_pending = True

    try:
        tavus.interrupt()

    except Exception as error:
        interruption_pending = False
        interrupted_inference_id = None

        raise RouteError(
            str(error),
            500,
        ) from error

    return interrupted_inference_id


def dismiss_open_question(
    prefix: str | None = None,
) -> dict:
    """
    Close question mode without calling the reasoner
    and resume the interrupted sentence.

    Caller must hold playback_lock.
    """

    if orchestrator.phase != ConversationPhase.QUESTION_READY:
        raise RouteError(
            "There is no open question to dismiss."
        )

    if not tavus.connected:
        raise RouteError(
            "Tavus is not connected."
        )

    if (
        playback_tracker.utterance_id is not None
        or answer_playback_tracker.utterance_id is not None
        or untracked_playback_active
    ):
        raise RouteError(
            "A playback utterance is already pending."
        )

    turn = orchestrator.dismiss_question(prefix)

    if turn is None:
        return {
            "resumed": False,
        }

    PlaybackCoordinator(
        orchestrator,
        playback_tracker,
    ).register_utterance(
        turn.utterance_id
    )

    try:
        speak_text(
            turn.text
        )

    except Exception as error:
        recovery_controller.handle_resume_submission_error(
            orchestrator=orchestrator,
            narration_tracker=playback_tracker,
        )

        raise RouteError(
            "Resume submission uncertain. "
            "Narration ownership preserved: "
            f"{error}",
            500,
        ) from error

    logger.debug('%s', "[XQ QUESTION] Question mode dismissed. "
        f"Resumed utterance {turn.utterance_id}.")

    return {
        "resumed": True,
        "spoken": turn.text,
        "utterance_id": turn.utterance_id,
    }


def answer_open_question(question: str) -> dict:
    """
    Answer through the XQ engine and speak the answer.

    Caller must hold playback_lock.
    """

    if orchestrator.phase != ConversationPhase.QUESTION_READY:
        raise RouteError(
            "Interrupt narration and wait for it to stop "
            "before asking a question."
        )

    if not tavus.connected:
        raise RouteError(
            "Tavus is not connected."
        )

    # If the answer fails, the user gets a full timeout to retry.
    restart_question_mode_timer()

    state_before = engine.get_current_state()

    try:
        reasoning_active.set()
        try:
            answer = orchestrator.ask_question(question)
        finally:
            reasoning_active.clear()

    except Exception as error:
        restart_question_mode_timer()
        raise RouteError(
            str(error),
            500,
        ) from error

    state_after = engine.get_current_state()

    if state_after != state_before:
        raise RouteError(
            "Debrief state changed during question mode.",
            500,
        )

    # A separate tracker owns the answer; its ID is local to that tracker.
    answer_playback_tracker.arm(1)

    try:
        speak_text(answer)

    except Exception as error:
        # Echo delivery is uncertain. Preserve ownership; end session to recover.
        raise RouteError(
            str(error),
            500,
        ) from error

    return {
        "question": question,
        "answer": answer,
        "state_before": state_before.value,
        "state_after": state_after.value,
    }


def restart_question_mode_timer() -> None:
    """
    Give the user a full timeout from now.
    Caller must hold playback_lock.
    """

    global question_mode_deadline

    if QUESTION_MODE_TIMEOUT_SECONDS <= 0:
        question_mode_deadline = None
        return

    question_mode_deadline = (
        time.monotonic()
        + QUESTION_MODE_TIMEOUT_SECONDS
    )


def question_mode_seconds_left() -> float | None:
    if (
        question_mode_deadline is None
        or orchestrator.phase
        != ConversationPhase.QUESTION_READY
    ):
        return None

    return round(
        max(0.0, question_mode_deadline - time.monotonic()),
        1,
    )


def check_question_mode_timeout(
    now: float | None = None,
) -> dict | None:
    """
    Close question mode when nobody asked, dismissed or
    spoke for QUESTION_MODE_TIMEOUT_SECONDS, and resume
    the interrupted sentence (no reasoner call).

    Caller must hold playback_lock.
    """

    global question_mode_deadline

    if question_mode_deadline is None:
        return None

    if (
        session_ending
        or orchestrator.phase
        != ConversationPhase.QUESTION_READY
    ):
        question_mode_deadline = None
        return None

    if now is None:
        now = time.monotonic()

    # Talking or a transcript on its way counts as activity.
    if http_voice_pending or voice_pipeline.busy():
        question_mode_deadline = (
            now + QUESTION_MODE_TIMEOUT_SECONDS
        )
        return None

    if now < question_mode_deadline:
        return None

    question_mode_deadline = None

    try:
        resumed = dismiss_open_question(
            orchestrator.TIMEOUT_PREFIX
        )

    except RouteError as error:
        # Try again after another full timeout, not every tick.
        question_mode_deadline = (
            now + QUESTION_MODE_TIMEOUT_SECONDS
        )

        return record_voice_event(
            "question_timeout_failed",
            error=error.message,
        )

    return record_voice_event(
        "question_timed_out",
        timeout_seconds=QUESTION_MODE_TIMEOUT_SECONDS,
        **resumed,
    )


def run_question_mode_watchdog() -> None:
    while not background_stop.wait(QUESTION_TIMEOUT_POLL_SECONDS):

        try:
            with playback_lock:
                check_question_mode_timeout()

        except Exception:
            logger.warning('%s', "[XQ QUESTION] Question mode "
                "timeout check failed.")
            traceback.print_exc()


def record_voice_event(
    action: str,
    **details,
) -> dict:
    global last_voice_event

    last_voice_event = {
        "action": action,
        "at": time.time(),
        **details,
    }

    logger.debug('%s', f"[XQ VOICE] {action}: {details}")

    return last_voice_event


def voice_interrupt_request_fresh() -> bool:
    """
    Caller must hold playback_lock.
    Expire a barge-in whose sentence never started.
    """

    global voice_interrupt_requested_at

    if voice_interrupt_requested_at is None:
        return False

    age = time.monotonic() - voice_interrupt_requested_at

    if age > VOICE_INTERRUPT_REQUEST_TTL_SECONDS:
        voice_interrupt_requested_at = None
        record_voice_event(
            "interrupt_request_expired",
            age_seconds=round(age, 2),
        )
        return False

    return True


def honour_voice_interrupt_request() -> None:
    """
    Called with playback_lock held when a tracked
    sentence starts after the user began speaking.
    """

    global voice_interrupt_requested_at

    if not voice_interrupt_request_fresh():
        return

    voice_interrupt_requested_at = None

    try:
        inference_id = request_interruption()

    except RouteError as error:
        record_voice_event(
            "interrupt_failed",
            error=error.message,
        )
        return

    record_voice_event(
        "interrupt_requested",
        inference_id=inference_id,
        deferred=True,
    )


def handle_voice_speech_started(
    participant_id: str,
) -> bool:
    """
    The user began talking: interrupt narration.
    Question mode opens once Tavus confirms the stop.
    """

    global voice_interrupt_requested_at

    with playback_lock:
        if (
            session_ending
            or not active_tavus_conversation_id
        ):
            return False

        if (
            orchestrator.phase
            == ConversationPhase.QUESTION_READY
        ):
            # The user is answering the open question.
            restart_question_mode_timer()
            return True

        if interruption_pending:
            return True

        # An answer is playing.
        if orchestrator.phase != ConversationPhase.NARRATING:
            return False

        if not tracked_playback_active():
            record_voice_event(
                "speech_ignored",
                participant_id=participant_id,
                reason="No tracked narration is playing.",
            )
            return False

        if playback_tracker.inference_id is None:
            voice_interrupt_requested_at = time.monotonic()

            record_voice_event(
                "interrupt_deferred",
                participant_id=participant_id,
                reason="Waiting for Tavus to start the sentence.",
            )
            return True

        try:
            inference_id = request_interruption()

        except RouteError as error:
            record_voice_event(
                "interrupt_failed",
                participant_id=participant_id,
                error=error.message,
            )
            return False

        record_voice_event(
            "interrupt_requested",
            participant_id=participant_id,
            inference_id=inference_id,
        )
        return True


def wait_for_voice_question_mode(
    timeout_seconds: float = VOICE_QUESTION_WAIT_SECONDS,
) -> None:
    """
    A short utterance can finish before Tavus confirms
    the stop. Wait (without the lock) for that first.
    """

    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        with playback_lock:
            if (
                not interruption_pending
                and not voice_interrupt_request_fresh()
            ):
                return

        time.sleep(0.05)


def route_voice_transcript(
    text: str,
    participant_id: str,
) -> dict:
    """
    Decide what a transcript does in question mode.

    Caller must hold playback_lock.
    """

    if orchestrator.phase != ConversationPhase.QUESTION_READY:
        return record_voice_event(
            "transcript_ignored",
            participant_id=participant_id,
            transcript=text,
            reason=(
                "Question mode is not open "
                f"(phase={orchestrator.phase.value})."
            ),
        )

    restart_question_mode_timer()
    result = classify_question_mode_utterance(text)

    if result.intent == VoiceIntent.EMPTY:
        return record_voice_event(
            "still_listening",
            participant_id=participant_id,
            transcript=text,
        )

    if result.intent == VoiceIntent.DISMISS:
        resumed = dismiss_open_question()

        return record_voice_event(
            "question_dismissed",
            participant_id=participant_id,
            transcript=text,
            matched_phrases=list(result.matched_phrases),
            **resumed,
        )

    answered = answer_open_question(result.text)

    return record_voice_event(
        "question_answered",
        participant_id=participant_id,
        transcript=text,
        **answered,
    )


def handle_voice_transcript(
    participant_id: str,
    text: str,
) -> None:
    with playback_lock:
        if (
            session_ending
            or not active_tavus_conversation_id
        ):
            record_voice_event(
                "transcript_ignored",
                participant_id=participant_id,
                transcript=text,
                reason="No active session.",
            )
            return

        try:
            route_voice_transcript(
                text,
                participant_id,
            )

        except RouteError as error:
            record_voice_event(
                "transcript_failed",
                participant_id=participant_id,
                transcript=text,
                error=error.message,
            )


def voice_question_context():
    """Identify the open question while the caller holds playback_lock."""
    if (session_ending or not active_tavus_conversation_id
            or orchestrator.phase != ConversationPhase.QUESTION_READY):
        return None
    return voice_session_generation, question_mode_generation


voice_pipeline = VoiceInputPipeline(
    transcriber=speech_transcriber,
    on_speech_started=handle_voice_speech_started,
    on_transcript=handle_voice_transcript,
    scorer_factory=create_speech_scorer,
    callback_lock=playback_lock,
    before_transcript=wait_for_voice_question_mode,
    get_question_context=voice_question_context,
    config=SegmenterConfig(
        speech_threshold=float(
            os.getenv("XQ_VAD_THRESHOLD", "0.6")
        ),
        end_silence_ms=int(
            os.getenv("XQ_VOICE_END_SILENCE_MS", "700")
        ),
    ),
)

tavus.on_user_audio = voice_pipeline.feed_audio
tavus.on_user_audio_closed = voice_pipeline.drop_participant

voice_pipeline.start()

if QUESTION_MODE_TIMEOUT_SECONDS > 0:
    Thread(
        target=run_question_mode_watchdog,
        name="xq-question-timeout",
        daemon=True,
    ).start()


# =========================================================
# PAGE
# =========================================================

@app.get("/")
def index():
    if not EXPERIENCE.business:
        return render_template("products.html")
    return render_template(EXPERIENCE.template("start.html"))


@app.get("/profiles")
def profile_menu():
    return render_template(EXPERIENCE.template("start.html"))


@app.get("/debrief")
def debrief_page():
    return render_template(
        EXPERIENCE.template("index.html")
    )


def save_assessment_persona(persona):
    with playback_lock:
        if persona.get('experience', 'family') != EXPERIENCE.name:
            raise DraftConflict('This profile belongs to a different workspace experience.')
        if session_starting or session_ending or active_tavus_conversation_id:
            raise DraftConflict("End the active session before adding a profile.")
        return repository.save_persona(persona, PERSONA_DIR)


app.config["SAVE_ASSESSMENT_PERSONA"] = save_assessment_persona


@app.before_request
def require_selected_business_profile():
    if (EXPERIENCE.business and (repository.active_person_id is None or not hasattr(engine, 'persona_path')) and request.method == 'POST'
            and (request.path.startswith('/api/debrief/') or request.path.startswith('/api/question')
                 or request.path == '/api/voice/audio')):
        return error_response('Select a workplace profile before using conversation controls.', 409)


def family_roster_snapshot():
    with playback_lock:
        members = repository.list_members(debrief_enabled_only=True)
        return {
            "family_id": repository.family_id,
            "family_name": repository.family_name,
            "members": [
                {key: member[key] for key in ("person_id", "display_name", "family_role")}
                for member in members
            ],
        }


def family_pair_snapshot(person_a_id, person_b_id):
    return family_members_snapshot([person_a_id, person_b_id])


def family_members_snapshot(person_ids):
    # Serialize only the snapshot with roster writes. Never change active_person_id.
    with playback_lock:
        personas = []
        for person_id in person_ids:
            if not repository.has_person(person_id):
                raise FamilySelectionError("That family member is unavailable. Reload the family roster.", 404)
            if not repository.get_member(person_id)["debrief_enabled"]:
                raise FamilySelectionError("That profile is not enabled for family comparisons.", 409)
            personas.append(deepcopy(repository.get_persona(person_id)))
        return tuple(personas)


def create_family_reasoner():
    # Lazy construction keeps model configuration/failures out of app startup.
    from openai import OpenAI
    from comparison_reasoner import ComparisonReasoner
    return ComparisonReasoner(
        client=OpenAI(timeout=30.0, max_retries=0),
        knowledge_dir=EXPERIENCE.knowledge_dir,
        experience=EXPERIENCE.name,
    )


def create_family_group_reasoner():
    from openai import OpenAI
    from family_group_reasoner import FamilyGroupReasoner
    return FamilyGroupReasoner(
        client=OpenAI(timeout=30.0, max_retries=0),
        knowledge_dir=EXPERIENCE.knowledge_dir,
        experience=EXPERIENCE.name,
    )


app.register_blueprint(create_family_blueprint(
    roster_snapshot=family_roster_snapshot,
    pair_snapshot=family_pair_snapshot,
    reasoner_factory=create_family_reasoner,
    group_snapshot=family_members_snapshot,
    group_reasoner_factory=create_family_group_reasoner,
    experience=EXPERIENCE.name,
))


#==========================================================
#PERSONAS
#==========================================================
@app.get("/api/personas")
def list_personas():
    return jsonify({
        "personas": get_available_personas()
    })


#==========================================================
#PERSON SELECT
#==========================================================

@app.post("/api/person/select")
@serialized_route
def select_person():
    global engine, orchestrator, playback_tracker, answer_playback_tracker
    global untracked_playback_active, untracked_inference_id
    global interruption_pending, interrupted_inference_id

    with playback_lock:
        if (
        session_starting
        or session_ending
        or active_tavus_conversation_id
    ):
            return error_response(
            "Cannot switch profiles while a Tavus "
            "session is active or changing state.",
            409,
        )

    payload = request.get_json(
        silent=True
    ) or {}

    filename = payload.get(
        "file"
    )

    if not filename:
        return error_response(
            "Persona file is required."
        )

    allowed = {
        item["file"]
        for item in get_available_personas()
    }

    if filename not in allowed:
        return error_response(
            "Unknown persona.",
            404,
        )

    selected_person = next(
        item
        for item in get_available_personas()
        if item["file"] == filename
    )

    person_id = selected_person["person_id"]

    if not person_id:
        return error_response(
            "Selected persona does not define a person_id.",
            500,
        )

    try:
        repository.set_active_person(
            person_id
        )

        engine = create_engine_for_active_person()

    except Exception as error:
        return error_response(
            str(error),
            500,
        )

    orchestrator = ConversationOrchestrator(
        engine
    )

    for tracker in (playback_tracker, answer_playback_tracker):
        if tracker.inference_id:
            retired_inference_ids.add(tracker.inference_id)
    if untracked_inference_id:
        retired_inference_ids.add(untracked_inference_id)
    playback_tracker = PlaybackEventTracker()
    answer_playback_tracker = PlaybackEventTracker()
    interruption_pending = False
    interrupted_inference_id = None
    untracked_inference_id = None
    untracked_playback_active = False
    recovery_controller.reset()
    reset_voice_state()

    return jsonify({
        "ok": True,
        "selected_person": (
            engine.display_name
        ),
        "state": (
            engine.get_current_state().name
        ),
    })


# =========================================================
# STATUS
# =========================================================

@app.get("/api/status")
def status():
    return jsonify({
        "ok": True,
        **current_payload(),
    })


@app.get("/api/playback/latency")
def playback_latency_status():
    with playback_lock:
        return jsonify(playback_latency.snapshot())


@app.get("/api/activity")
def activity_status():
    # Observational snapshot: do not wait on the playback lock held by reasoning.
    # This endpoint contains no transcript, scores, prompt, or generated narrative.
    active = bool(active_tavus_conversation_id)
    pending = any(tracker.utterance_id is not None for tracker in (playback_tracker, answer_playback_tracker)) or untracked_playback_active
    speaking = any(tracker.inference_id is not None for tracker in (playback_tracker, answer_playback_tracker)) or untracked_inference_id is not None
    question_ready = orchestrator.phase == ConversationPhase.QUESTION_READY
    code, title, detail = describe_activity(
        active=active, connected=tavus.connected, starting=session_starting,
        ending=session_ending, reasoning=reasoning_active.is_set() or (LOCAL_PLAYBACK and http_voice_pending),
        interrupted=interruption_pending, question_ready=question_ready,
        pending=pending, speaking=speaking, voice_busy=voice_pipeline.busy(), experience=EXPERIENCE.name,
    )
    if LOCAL_PLAYBACK:
        if code == 'connecting':
            title, detail = 'Warming up the local voice', 'Loading Kokoro on this computer. The first start takes longer.'
        elif code == 'ending':
            detail = 'Stopping local audio and releasing this conversation.'
        elif code == 'disconnected':
            title, detail = 'Local audio unavailable', 'End the conversation before trying again.'
    response = jsonify(code=code, title=title, detail=detail,
                       active=active, connected=tavus.connected,
                       changing=session_starting or session_ending,
                       pending=pending, question_ready=question_ready,
                       phase=orchestrator.phase.value, interrupted=interruption_pending,
                       answer_pending=answer_playback_tracker.utterance_id is not None,
                       state=engine.get_current_state().value,
                       person_id=repository.active_person_id)
    response.headers["Cache-Control"] = "no-store"
    return response


# =========================================================
# SESSION LIFECYCLE
# =========================================================


@app.post("/api/session/start")
def start_session():
    global active_tavus_conversation_id
    global session_starting

    # Reserve the session before contacting Tavus.
    with playback_lock:
        if repository.active_person_id is None or (EXPERIENCE.business and not hasattr(engine, 'persona_path')):
            return error_response('Select a workplace profile before starting a conversation.', 409)
        if (
            session_starting
            or session_ending
            or active_tavus_conversation_id
        ):
            return error_response(
                "A Tavus session is already active "
                "or being established.",
                409,
            )

        session_starting = True

    try:
        # Do not hold the lock during network operations.
        conversation = (tavus.create_conversation(conversation_name='XQ Workplace Debrief')
                        if EXPERIENCE.business else tavus.create_conversation())

        with playback_lock:
            active_tavus_conversation_id = (
                conversation["conversation_id"]
            )

        backend_joined = wait_for_tavus_connection()

        voice_error = None

        if backend_joined:
            try:
                tavus.listen_to_existing_participants()

            except Exception as error:
                voice_error = str(error)

                logger.warning('%s', "[XQ VOICE] Could not attach to "
                    f"participants already in the room: {error}")

        return jsonify({
            "ok": True,
            "conversation": {
                "conversation_id": (
                    conversation["conversation_id"]
                ),
                "conversation_url": (
                    conversation["conversation_url"]
                ),
                "meeting_token": (
                    conversation.get("meeting_token")
                ),
            },
            "backend_joined": backend_joined,
            "voice_error": voice_error,
            "voice_user_name": tavus.voice_user_name,
            **current_payload(),
        })

    except Exception as error:
        return error_response(
            str(error),
            500,
        )

    finally:
        with playback_lock:
            session_starting = False


@app.post("/api/session/end")
def end_session():
    global active_tavus_conversation_id, untracked_playback_active
    global interruption_pending
    global interrupted_inference_id

    global session_ending, untracked_inference_id, orchestrator

    with playback_lock:
        if session_starting:
            return error_response("Cannot end a session while its connection is being established.", 409)

        if session_ending:
            return error_response("Session shutdown is in progress.", 409)

        session_ending = True

    # Daily may wait on a callback while disconnecting: do not hold the lock.
    try:
        if active_tavus_conversation_id:
            tavus.end_conversation()
        else:
            tavus.disconnect()
    except Exception as error:
        with playback_lock:
            session_ending = False
        return error_response(str(error), 500)

    with playback_lock:
        for tracker in (playback_tracker, answer_playback_tracker):
            if tracker.inference_id:
                retired_inference_ids.add(tracker.inference_id)
            tracker.clear()
        if untracked_inference_id:
            retired_inference_ids.add(untracked_inference_id)
        engine.exit_question_mode()
        orchestrator = ConversationOrchestrator(engine)
        active_tavus_conversation_id = None
        untracked_playback_active = False
        untracked_inference_id = None
        interruption_pending = False
        interrupted_inference_id = None
        recovery_controller.reset()
        reset_voice_state()
        session_ending = False
    return jsonify({"ok": True, "message": "Session ended."})


# =========================================================
# DEBRIEF DELIVERY
# =========================================================

@app.post("/api/debrief/speak")
@playback_route
def speak_current_section():
    """
    Speak the current deterministic section.

    This is intentionally separate from session/start
    so the browser can finish joining the Daily iframe
    before the PAL begins speaking.
    """
    with playback_lock:
        if interruption_in_progress():
            return error_response(
                "An interruption is pending. "
                "Wait for Tavus to stop speaking.",
                409,
            )

        if tracked_playback_active():
            return error_response(
                "A tracked sentence is still playing. Wait for it to finish.",
                409,
            )

        text = engine.get_current_content()
        
        try:
            play_section_text(text)

        except Exception as error:
            return error_response(
                str(error),
                500,
            )

        return jsonify({
            "ok": True,
            "spoken": text,
            **current_payload(),
        })


@app.post("/api/debrief/sentence/test")
@playback_route
def test_sentence_playback():
    """
    Diagnostic endpoint: speak only the first sentence
    of the current section.

    Does not advance the engine, orchestrator, or cursor.
    """

    if not tavus.connected:
        return error_response(
            "The Tavus backend client is not connected.",
            409,
        )

    # Do not overlap this diagnostic with tracked playback.
    if playback_tracker.utterance_id is not None:
        return error_response(
            "A playback utterance is already pending.",
            409,
        )

    sentences = split_sentences(
        engine.get_current_content()
    )

    if not sentences:
        return error_response(
            "The current section has no sentences.",
            409,
        )

    first_sentence = sentences[0]

    try:
        speak_text(first_sentence)

    except Exception as error:
        return error_response(
            str(error),
            500,
        )

    return jsonify({
        "ok": True,
        "spoken": first_sentence,
        "sentence_count": len(sentences),
        **current_payload(),
    })


# =========================================================
# DEBRIEF ROUTES
# =========================================================

@app.post("/api/debrief/next")
@playback_route
def next_section():
    with playback_lock:
        if interruption_in_progress():
            return error_response(
                "An interruption is pending. "
                "Wait for Tavus to stop speaking.",
                409,
            )

        if tracked_playback_active():
            return error_response(
                "A tracked sentence is still playing. "
                "Wait for it to finish before advancing.",
                409,
            )

        if untracked_playback_active:
            return error_response(
                "Tavus is already speaking another response.",
                409,
            )

        try:
            if (
                engine.get_current_state()
                != DebriefState.COMPLETE
            ):
                engine.advance()

            turn = submit_next_tracked_sentence()

        except Exception as error:
            return error_response(
                str(error),
                500,
            )

        if turn is None:
            return jsonify({
                "ok": True,
                "finished": True,
                **current_payload(),
            })

        return jsonify({
            "ok": True,
            "spoken": turn.text,
            "utterance_id": turn.utterance_id,
            "awaiting_playback_completion": True,
            **current_payload(),
        })


@app.post("/api/debrief/tracked/next")
@playback_route
def tracked_next_sentence():
    with playback_lock:
        if interruption_in_progress():
            return error_response(
                "An interruption is pending. "
                "Wait for Tavus to stop speaking.",
                409,
    )

        if (
            not active_tavus_conversation_id
            or not tavus.connected
        ):
            return error_response(
                "Start and join a Tavus session first.",
                409,
            )

        if playback_tracker.utterance_id is not None:
            return error_response(
                "A tracked sentence is still playing.",
                409,
            )

        if untracked_playback_active:
            return error_response(
                "Tavus is already speaking another response.",
                409,
            )

        try:
            turn = submit_next_tracked_sentence()

        except Exception as error:
            return error_response(
                str(error),
                500,
            )

        if turn is None:
            return jsonify({
                "ok": True,
                "finished": True,
                "message": "No more sentences in this section.",
                "sentence_index": (
                    orchestrator.cursor.sentence_index
                ),
            })

        return jsonify({
            "ok": True,
            "utterance_id": turn.utterance_id,
            "spoken": turn.text,
            "sentence_index": (
                orchestrator.cursor.sentence_index
            ),
            "awaiting_playback_completion": True,
        })


@app.post("/api/debrief/repeat")
@playback_route
def repeat_section():
    text = engine.get_current_content()

    with playback_lock:
        if interruption_in_progress():
            return error_response(
                "An interruption is pending. "
                "Wait for Tavus to stop speaking.",
                409,
            )

        if tracked_playback_active():
            return error_response(
                "A tracked sentence is still playing. Wait for it to finish.",
                409,
            )

        try:
            play_section_text(text)

        except Exception as error:
            return error_response(
                str(error),
                500,
            )

        return jsonify({
            "ok": True,
            "spoken": text,
            **current_payload(),
        })


@app.post("/api/debrief/restart")
@playback_route
def restart_debrief():

    with playback_lock:
        if interruption_in_progress():
            return error_response(
                "An interruption is pending. "
                "Wait for Tavus to stop speaking.",
                409,
            )

        if tracked_playback_active():
            return error_response(
                "A tracked sentence is still playing. Wait for it to finish.",
                409,
            )
        
        try:
            engine.reset()

            text = (
                engine.get_current_content()
            )

            play_section_text(text)

        except Exception as error:
            return error_response(
                str(error),
                500,
            )

        return jsonify({
            "ok": True,
            "spoken": text,
            **current_payload(),
        })


# =========================================================
# INTERRUPTION
# =========================================================

@app.post("/api/debrief/interrupt")
@serialized_route
def interrupt_debrief():
    with playback_lock:
        if (tavus.connected and not interruption_pending
                and not tracked_playback_active()
                and answer_playback_tracker.utterance_id is None
                and not untracked_playback_active
                and orchestrator.phase == ConversationPhase.NARRATING):
            orchestrator.open_question()
            restart_question_mode_timer()
            return jsonify({"ok": True, "interruption_pending": False,
                            "interrupted_inference_id": None})
        try:
            request_interruption()

        except RouteError as error:
            return error_response(
                error.message,
                error.status_code,
            )

        return jsonify({
            "ok": True,
            "interruption_pending": True,
            "interrupted_inference_id": (
                interrupted_inference_id
            ),
        })


# =========================================================
# XQ QUESTION MODE
# =========================================================

@app.post("/api/question")
@playback_route
def ask_question():

    with playback_lock:
        if interruption_in_progress():
            return error_response(
                "An interruption is pending. "
                "Wait for Tavus to stop speaking.",
                409,
            )

        if tracked_playback_active():
            return error_response(
                "A tracked sentence is still playing. Wait for it to finish.",
                409,
            )
        
        body = (
            request.get_json(
                silent=True
            )
            or {}
        )

        question = str(
            body.get(
                "question",
                "",
            )
        ).strip()

        if not question:
            return error_response(
                "A question is required."
            )

        # "Never mind", "continue", ... close question
        # mode without calling the reasoner.
        intent = classify_question_mode_utterance(question)

        try:
            if intent.intent == VoiceIntent.DISMISS:
                resumed = dismiss_open_question()

                return jsonify({
                    "ok": True,
                    "question": question,
                    "dismissed": True,
                    "matched_phrases": list(
                        intent.matched_phrases
                    ),
                    **resumed,
                    **current_payload(),
                })

            if intent.intent == VoiceIntent.EMPTY:
                if orchestrator.phase != ConversationPhase.QUESTION_READY:
                    raise RouteError("Question mode is not open.")
                restart_question_mode_timer()
                return jsonify({"ok": True, "still_listening": True, **current_payload()})

            answered = answer_open_question(question)

        except RouteError as error:
            return error_response(
                error.message,
                error.status_code,
            )

        except Exception as error:
            return error_response(
                str(error),
                500,
            )

        return jsonify({
            "ok": True,
            **answered,
            **current_payload(),
        })


@app.post("/api/question/dismiss")
@serialized_route
def dismiss_question():
    """
    Leave question mode without asking anything and
    resume the interrupted sentence (UI button).
    """

    with playback_lock:
        if interruption_in_progress():
            return error_response(
                "An interruption is pending. "
                "Wait for Tavus to stop speaking.",
                409,
            )

        try:
            resumed = dismiss_open_question()

        except RouteError as error:
            return error_response(
                error.message,
                error.status_code,
            )

        except Exception as error:
            return error_response(
                str(error),
                500,
            )

        return jsonify({
            "ok": True,
            "dismissed": True,
            **resumed,
            **current_payload(),
        })


@app.post("/api/question/keepalive")
@serialized_route
def keep_question_mode_open():
    """
    Restart the question-mode timeout, e.g. while
    the user is typing a question.
    """

    if orchestrator.phase != ConversationPhase.QUESTION_READY:
        return error_response(
            "Question mode is not open.",
            409,
        )

    restart_question_mode_timer()

    return jsonify({
        "ok": True,
        "question_mode_seconds_left": (
            question_mode_seconds_left()
        ),
    })


# =========================================================
# VOICE INPUT (HTTP)
# =========================================================

@app.post("/api/voice/audio")
def voice_audio():
    """Transcribe one uploaded utterance without blocking playback callbacks."""
    global http_voice_pending

    extension = AUDIO_CONTENT_TYPES.get((request.mimetype or "").lower())
    if extension is None:
        return error_response("Unsupported audio type.", 415)
    audio = request.get_data(cache=False)
    if not audio:
        return error_response("The request body must contain audio.")

    with playback_lock:
        if session_ending or not active_tavus_conversation_id or not tavus.connected:
            return error_response("Start and join a Tavus session first.", 409)
        if http_voice_pending or voice_pipeline.busy():
            return error_response("A voice utterance is already being processed.", 409)
        generation = voice_session_generation
        if not handle_voice_speech_started("http"):
            return error_response("Interrupt tracked narration before asking a question.", 409)
        http_voice_pending = True

    try:
        wait_for_voice_question_mode()
        with playback_lock:
            if generation != voice_session_generation or session_ending:
                return error_response("The voice session changed.", 409)
            if orchestrator.phase != ConversationPhase.QUESTION_READY:
                return error_response("Narration has not stopped yet. Try again.", 409)
            # A typed answer or dismissal may finish while transcription runs.
            question_turn = question_mode_generation

        transcript = speech_transcriber.transcribe_file(audio, extension)

        with playback_lock:
            if (generation != voice_session_generation or session_ending
                    or question_turn != question_mode_generation
                    or orchestrator.phase != ConversationPhase.QUESTION_READY):
                return error_response("The voice question is no longer active.", 409)
            outcome = route_voice_transcript(transcript, "http")
            return jsonify({
                "ok": True,
                "transcript": transcript,
                "voice_result": outcome,
                **current_payload(),
            })
    except RouteError as error:
        return error_response(error.message, error.status_code)
    except ValueError as error:
        return error_response(str(error))
    except Exception as error:
        return error_response(f"Voice input failed: {error}", 502)
    finally:
        with playback_lock:
            if generation == voice_session_generation:
                http_voice_pending = False
                if orchestrator.phase == ConversationPhase.QUESTION_READY:
                    restart_question_mode_timer()


#==========================================================
#DISC NARRATIVE
#==========================================================

@app.post("/api/dev/disc-narrative")
@playback_route
def dev_disc_narrative():
    text = engine.get_disc_narrative()

    speak_text(text)

    return jsonify({
        "ok": True,
        "text": text,
    })

@app.post("/api/dev/driving-forces-narrative")
@playback_route
def dev_driving_forces_narrative():
    text = engine.get_driving_forces_narrative()

    speak_text(text)

    return jsonify({
        "ok": True,
        "text": text,
    })

@app.post("/api/dev/eq-narrative")
@playback_route
def dev_eq_narrative():
    text = engine.get_eq_narrative()

    speak_text(text)

    return jsonify({
        "ok": True,
        "text": text,
    })

@app.post("/api/dev/integrated-narrative")
@playback_route
def dev_integrated_narrative():
    text = engine.get_integrated_narrative()

    speak_text(text)

    return jsonify({
        "ok": True,
        "text": text,
    })

# =========================================================
# STARTUP
# =========================================================

if not EXPERIENCE.business:
    from presentation import create_presentation_blueprint
    app.register_blueprint(create_presentation_blueprint())
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from workspace_host import LazyBusinessApplication
    business_application = LazyBusinessApplication()
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {'/business': business_application})

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False,
    )
