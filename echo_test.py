import sys

from flask import Flask, jsonify, request
from daily import CallClient, Daily, EventHandler

from debrief_engine import DebriefEngine
from family_repository import FamilyRepository


app = Flask(__name__)

call_client = None

FAMILY_MANIFEST_PATH = (
    "data/families/demo_family.json"
)

repository = FamilyRepository(
    FAMILY_MANIFEST_PATH
)

active_member = (
    repository.get_active_member()
)

engine = DebriefEngine(
    active_member["persona_file"]
)

def send_echo(
    conversation_id: str,
    text: str,
) -> None:
    global call_client

    message = {
        "message_type": "conversation",
        "event_type": "conversation.echo",
        "conversation_id": conversation_id,
        "properties": {
            "modality": "text",
            "text": text,
            "done": True,
        },
    }

    call_client.send_app_message(
        message
    )

@app.post("/xq/introduction")
def xq_introduction():
    body = request.json or {}

    conversation_id = body.get(
        "conversation_id"
    )

    if not conversation_id:
        return jsonify({
            "error": (
                "conversation_id is required."
            )
        }), 400

    text = engine.get_current_content()

    send_echo(
        conversation_id=conversation_id,
        text=text,
    )

    return jsonify({
        "state": (
            engine.get_current_state().value
        ),
        "text": text,
    })

class RoomHandler(EventHandler):
    def on_app_message(
        self,
        message,
        sender: str,
    ) -> None:
        print(
            f"Incoming app message from "
            f"{sender}: {message}"
        )


def join_room(url: str) -> None:
    global call_client

    Daily.init()

    handler = RoomHandler()

    call_client = CallClient(
        event_handler=handler
    )

    call_client.join(url)

    print(
        f"Joined room: {url}"
    )


@app.post("/send_text_message")
def send_text_message():
    global call_client

    if not call_client:
        return jsonify({
            "error": "Not connected to a room."
        }), 400

    body = request.json or {}

    send_echo(
        conversation_id=body[
            "conversation_id"
        ],
        text=body["text"],
    )

    return jsonify({
        "status": "Message sent successfully."
    })

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python echo_test.py "
            "<conversation_url>"
        )
        raise SystemExit(1)

    join_room(
        sys.argv[1]
    )

    app.run(
        port=8000,
        debug=False,
    )