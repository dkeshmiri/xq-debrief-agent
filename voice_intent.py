import re
from dataclasses import dataclass
from enum import Enum


class VoiceIntent(str, Enum):
    """
    What a transcript means while question mode is open.
    """

    # Send the transcript to the XQ reasoning engine.
    QUESTION = "question"

    # Leave question mode and resume narration.
    # No API call is made.
    DISMISS = "dismiss"

    # Only filler ("um", "wait", "thank you").
    # Stay in question mode and keep listening.
    EMPTY = "empty"


@dataclass(frozen=True)
class VoiceIntentResult:
    intent: VoiceIntent
    text: str
    matched_phrases: tuple[str, ...] = ()


# Phrases that mean "no question, carry on".
# Written lowercase and without apostrophes,
# because the transcript is normalized that way.
DISMISSAL_PHRASES = (
    "never mind",
    "nevermind",
    "never mind that",
    "nvm",
    "forget it",
    "forget that",
    "forget about it",
    "ignore that",
    "ignore me",
    "scratch that",
    "my mistake",
    "my bad",
    "my apologies",
    "sorry",
    "im sorry",
    "sorry about that",
    "continue",
    "please continue",
    "you can continue",
    "lets continue",
    "go on",
    "go ahead",
    "keep going",
    "carry on",
    "proceed",
    "resume",
    "move on",
    "false alarm",
    "wrong button",
    "didnt mean to",
    "i didnt mean to",
    "didnt mean to interrupt",
    "i didnt mean to interrupt",
    "no question",
    "no questions",
    "not a question",
    "nothing",
    "its nothing",
    "thats all",
    "thats it",
    "all good",
    "its fine",
    "its ok",
    "its okay",
    "no worries",
)

# Words and phrases that carry no question on their own.
# They never trigger a dismissal by themselves, and they
# never turn a dismissal into a question either.
# Includes common speech-to-text output for silence.
FILLER_PHRASES = (
    "oh",
    "oops",
    "um",
    "umm",
    "uh",
    "uhh",
    "er",
    "erm",
    "ah",
    "hmm",
    "hm",
    "mm",
    "ok",
    "okay",
    "alright",
    "all right",
    "right",
    "please",
    "just",
    "actually",
    "yeah",
    "yes",
    "yep",
    "no",
    "nope",
    "nah",
    "well",
    "so",
    "and",
    "then",
    "hey",
    "hi",
    "hello",
    "wait",
    "hold on",
    "hang on",
    "one second",
    "one sec",
    "excuse me",
    "thanks",
    "thank you",
    "thanks for watching",
    "question",
    "quick question",
    "i have a question",
    "can i ask",
    "can i ask a question",
    "let me ask",
    "you",
    "can",
)

_NON_WORD = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def _tokens(phrase: str) -> tuple[str, ...]:
    return tuple(phrase.split())


# Longest phrases first, so "never mind that" wins
# over "never mind".
_DISMISSAL_TOKENS = sorted(
    {_tokens(phrase) for phrase in DISMISSAL_PHRASES},
    key=len,
    reverse=True,
)

_FILLER_TOKENS = sorted(
    {_tokens(phrase) for phrase in FILLER_PHRASES},
    key=len,
    reverse=True,
)


def normalize_transcript(text: str) -> str:
    """
    Lowercase, drop apostrophes and punctuation,
    collapse whitespace.
    """

    lowered = (
        text.lower()
        .replace("’", "")
        .replace("'", "")
    )

    without_punctuation = _NON_WORD.sub(
        " ",
        lowered,
    )

    return _SPACES.sub(
        " ",
        without_punctuation,
    ).strip()


def _match_at(
    words: list[str],
    position: int,
    candidates: list[tuple[str, ...]],
) -> tuple[str, ...] | None:
    for candidate in candidates:
        end = position + len(candidate)

        if tuple(words[position:end]) == candidate:
            return candidate

    return None


def classify_question_mode_utterance(
    text: str,
) -> VoiceIntentResult:
    """
    Decide whether a question-mode transcript is a
    question, a dismissal, or nothing at all.

    Conservative by design: the transcript is a
    dismissal only when EVERY word belongs to a
    dismissal or filler phrase. "Never mind, what
    about my EQ?" is still a question.
    """

    cleaned = text.strip()
    words = normalize_transcript(cleaned).split()

    matched: list[str] = []
    position = 0

    while position < len(words):
        dismissal = _match_at(
            words,
            position,
            _DISMISSAL_TOKENS,
        )

        if dismissal is not None:
            matched.append(" ".join(dismissal))
            position += len(dismissal)
            continue

        filler = _match_at(
            words,
            position,
            _FILLER_TOKENS,
        )

        if filler is not None:
            position += len(filler)
            continue

        return VoiceIntentResult(
            intent=VoiceIntent.QUESTION,
            text=cleaned,
        )

    if matched:
        return VoiceIntentResult(
            intent=VoiceIntent.DISMISS,
            text=cleaned,
            matched_phrases=tuple(matched),
        )

    return VoiceIntentResult(
        intent=VoiceIntent.EMPTY,
        text=cleaned,
    )
