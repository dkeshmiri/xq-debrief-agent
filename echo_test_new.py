import sys
from typing import Any

from daily import (
    CallClient,
    Daily,
    EventHandler,
)
from flask import (
    Flask,
    jsonify,
    request,
)

from debrief_engine import DebriefEngine
from debrief_state import DebriefState
from family_repository import FamilyRepository


# =========================================================
# CONFIGURATION
# =========================================================

FAMILY_MANIFEST_PATH = (
    "data/families/demo_family.json"
)

FLASK_HOST = "127.0.0.1"
FLASK_PORT = 8000


# =========================================================
# APPLICATION STATE
# =========================================================

app = Flask(__name__)

call_client: CallClient | None = None
conversation_id: str | None = None


# =========================================================
# XQ ENGINE SETUP
# =========================================================

repository = FamilyRepository(
    FAMILY_MANIFEST_PATH
)

active_member = (
    repository.get_active_member()
)

engine = DebriefEngine(
    active_member["persona_file"]
)


# =========================================================
# DAILY / TAVUS EVENTS
# =========================================================

class RoomHandler(EventHandler):
    """
    Minimal Daily event handler used only for diagnostics.
    """

    def on_app_message(
        self,
        message: Any,
        sender: str,
    ) -> None:
        print()
        print("[TAVUS APP MESSAGE]")
        print("Sender:", sender)
        print("Message:", message)


# =========================================================
# TAVUS CONNECTION
# =========================================================

def join_tavus_room(
    conversation_url: str,
) -> None:
    """
    Join the Tavus/Daily conversation.
    """

    global call_client

    Daily.init()

    handler = RoomHandler()

    call_client = CallClient(
        event_handler=handler
    )

    print()
    print("Joining Tavus conversation...")

    call_client.join(
        conversation_url
    )

    print("Join request sent.")


def send_echo(
    text: str,
) -> None:
    """
    Send already-approved text to the Tavus Echo PAL.

    Tavus does not reason over this text.
    It simply speaks it.
    """

    if call_client is None:
        raise RuntimeError(
            "The Tavus room is not connected."
        )

    if conversation_id is None:
        raise RuntimeError(
            "No Tavus conversation ID is configured."
        )

    cleaned_text = text.strip()

    if not cleaned_text:
        raise ValueError(
            "Cannot send empty text to Tavus."
        )

    message = {
        "message_type": "conversation",
        "event_type": "conversation.echo",
        "conversation_id": conversation_id,
        "properties": {
            "modality": "text",
            "text": cleaned_text,
            "done": True,
        },
    }

    call_client.send_app_message(
        message
    )

    print()
    print("[ECHO SENT]")
    print(cleaned_text)


# =========================================================
# RESPONSE HELPERS
# =========================================================

def current_state_payload() -> dict[str, Any]:
    """
    Return useful information about the current XQ state.
    """

    return {
        "active_person": engine.display_name,
        "state": (
            engine.get_current_state().value
        ),
        "content": (
            engine.get_current_content()
        ),
    }


def error_response(
    message: str,
    status_code: int = 400,
):
    return jsonify({
        "ok": False,
        "error": message,
    }), status_code


# =========================================================
# BASIC DIAGNOSTIC ROUTES
# =========================================================

@app.get("/health")
def health():
    """
    Verify that the local Flask harness is alive.
    """

    return jsonify({
        "ok": True,
        "service": "xq-tavus-echo-test",
        "active_person": engine.display_name,
        "state": (
            engine.get_current_state().value
        ),
        "tavus_connected": (
            call_client is not None
        ),
        "conversation_id_set": (
            conversation_id is not None
        ),
    })


@app.get("/xq/status")
def xq_status():
    return jsonify({
        "ok": True,
        **current_state_payload(),
    })


# =========================================================
# XQ → TAVUS ROUTES
# =========================================================

@app.post("/xq/introduction")
def xq_introduction():
    """
    Speak whatever deterministic XQ section is currently active.
    """

    try:
        text = engine.get_current_content()

        send_echo(
            text
        )

        return jsonify({
            "ok": True,
            "spoken": text,
            **current_state_payload(),
        })

    except Exception as error:
        return error_response(
            str(error),
            500,
        )


@app.post("/xq/next")
def xq_next():
    """
    Advance one deterministic XQ state and speak it.
    """

    try:
        if (
            engine.get_current_state()
            != DebriefState.COMPLETE
        ):
            engine.advance()

        text = engine.get_current_content()

        send_echo(
            text
        )

        return jsonify({
            "ok": True,
            "spoken": text,
            **current_state_payload(),
        })

    except Exception as error:
        return error_response(
            str(error),
            500,
        )


@app.post("/xq/repeat")
def xq_repeat():
    """
    Repeat the current deterministic XQ section.
    """

    try:
        text = engine.get_current_content()

        send_echo(
            text
        )

        return jsonify({
            "ok": True,
            "spoken": text,
            **current_state_payload(),
        })

    except Exception as error:
        return error_response(
            str(error),
            500,
        )


@app.post("/xq/restart")
def xq_restart():
    """
    Reset the active person's debrief and speak the introduction.
    """

    try:
        engine.reset()

        text = engine.get_current_content()

        send_echo(
            text
        )

        return jsonify({
            "ok": True,
            "spoken": text,
            **current_state_payload(),
        })

    except Exception as error:
        return error_response(
            str(error),
            500,
        )


@app.post("/xq/ask")
def xq_ask():
    """
    Ask the real XQ reasoning engine a question.

    The engine performs:
        guardrails
        routing
        context building
        reasoning
        validation

    Only the final returned answer is sent to Tavus.
    """

    body = request.get_json(
        silent=True
    ) or {}

    question = str(
        body.get(
            "question",
            "",
        )
    ).strip()

    if not question:
        return error_response(
            "The JSON body must contain a non-empty "
            "'question' field."
        )

    state_before = (
        engine.get_current_state()
    )

    engine.enter_question_mode()

    try:
        answer = engine.answer_question(
            question
        )

    except Exception as error:
        return error_response(
            str(error),
            500,
        )

    finally:
        engine.exit_question_mode()

    state_after = (
        engine.get_current_state()
    )

    if state_after != state_before:
        return error_response(
            "XQ state changed unexpectedly during "
            "question mode.",
            500,
        )

    try:
        send_echo(
            answer
        )

    except Exception as error:
        return error_response(
            str(error),
            500,
        )

    return jsonify({
        "ok": True,
        "question": question,
        "answer": answer,
        "state_before": state_before.value,
        "state_after": state_after.value,
    })


# =========================================================
# MANUAL ECHO TEST
# =========================================================

@app.post("/echo")
def manual_echo():
    """
    Send arbitrary text directly to Tavus.

    This is useful only for diagnosing the Tavus connection.
    It does NOT invoke the XQ engine.
    """

    body = request.get_json(
        silent=True
    ) or {}

    text = str(
        body.get(
            "text",
            "",
        )
    ).strip()

    if not text:
        return error_response(
            "The JSON body must contain a non-empty "
            "'text' field."
        )

    try:
        send_echo(
            text
        )

    except Exception as error:
        return error_response(
            str(error),
            500,
        )

    return jsonify({
        "ok": True,
        "spoken": text,
    })


# =========================================================
# STARTUP
# =========================================================

def main() -> None:
    global conversation_id

    if len(sys.argv) != 3:
        print()
        print(
            "Usage:"
        )
        print(
            "  python echo_test.py "
            "\"<conversation_url>\" "
            "\"<conversation_id>\""
        )
        print()

        raise SystemExit(1)

    conversation_url = (
        sys.argv[1].strip()
    )

    conversation_id = (
        sys.argv[2].strip()
    )

    if not conversation_url:
        raise ValueError(
            "Conversation URL cannot be empty."
        )

    if not conversation_id:
        raise ValueError(
            "Conversation ID cannot be empty."
        )

    print()
    print("=" * 60)
    print("XQ → TAVUS ECHO TEST")
    print("=" * 60)
    print()
    print(
        "Active person:",
        engine.display_name,
    )
    print(
        "XQ state:",
        engine.get_current_state().value,
    )
    print(
        "Conversation ID:",
        conversation_id,
    )

    join_tavus_room(
        conversation_url
    )

    print()
    print("Local test server starting...")
    print(
        f"http://{FLASK_HOST}:{FLASK_PORT}"
    )
    print()

    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()