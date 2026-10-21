import io
import os
import wave
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


# Bias recognition toward XQ vocabulary.
DEFAULT_TRANSCRIPTION_PROMPT = (
    "A family member is asking about their XQ "
    "assessment debrief: DISC, Natural and Adapted "
    "styles, Driving Forces, EQ, emotional "
    "intelligence, self-regulation, social awareness."
)

# Upload formats accepted by the transcription API,
# keyed by HTTP content type.
AUDIO_CONTENT_TYPES = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/flac": "flac",
}

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def pcm16_to_wav(
    pcm: bytes,
    sample_rate: int,
    channels: int = 1,
) -> bytes:
    """
    Wrap raw 16-bit PCM in a WAV container.
    """

    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)

    return buffer.getvalue()


class SpeechTranscriber:
    """
    Speech-to-text for user questions.

    Converts audio into text only. It does not decide
    what the text means or touch the debrief.
    """

    def __init__(
        self,
        client: Any | None = None,
        model: str | None = None,
        language: str = "en",
        prompt: str = DEFAULT_TRANSCRIPTION_PROMPT,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            api_key = os.getenv("OPENAI_API_KEY")

            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY was not found in the environment."
                )

            self.client = OpenAI(api_key=api_key)

        self.model = (
            model
            or os.getenv("XQ_STT_MODEL")
            or "gpt-4o-transcribe"
        )

        self.language = language
        self.prompt = prompt

    def transcribe_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        channels: int = 1,
    ) -> str:
        if not pcm:
            raise ValueError(
                "Cannot transcribe empty audio."
            )

        return self.transcribe_file(
            pcm16_to_wav(
                pcm,
                sample_rate,
                channels,
            ),
            extension="wav",
        )

    def transcribe_file(
        self,
        audio: bytes,
        extension: str,
    ) -> str:
        """
        Transcribe an encoded audio file.

        Returns the transcript, possibly empty when
        nothing intelligible was said.
        """

        if not audio:
            raise ValueError(
                "Cannot transcribe empty audio."
            )

        if len(audio) > MAX_UPLOAD_BYTES:
            raise ValueError(
                "Audio exceeds the 25 MB transcription limit."
            )

        result = self.client.audio.transcriptions.create(
            model=self.model,
            file=(
                f"utterance.{extension}",
                audio,
            ),
            language=self.language,
            prompt=self.prompt,
        )

        text = getattr(result, "text", None)

        if not isinstance(text, str):
            raise RuntimeError(
                "The transcription service returned "
                "no text field."
            )

        return text.strip()
