
import re


# Conservative first-pass sentence boundaries:
# punctuation, an optional closing quote, then whitespace.
_BOUNDARY = re.compile(
    r"""(?<=[.!?])(?P<closing>["”’']?)\s+"""
)

# Titles and abbreviations that should not end a sentence.
_ABBREVIATIONS = {
    "dr.",
    "mr.",
    "mrs.",
    "ms.",
    "prof.",
    "sr.",
    "jr.",
    "e.g.",
    "i.e.",
}


def split_sentences(text: str) -> list[str]:
    """
    Split narrative text into speakable sentences.

    Preserve the original wording and punctuation.
    Prefer keeping two sentences together over
    splitting incorrectly.
    """

    if not text.strip():
        return []

    text = text.strip()
    sentences = []
    start = 0

    for match in _BOUNDARY.finditer(text):
        before_boundary = text[start:match.start()]
        closing_quote = match.group("closing")

        candidate = (
            before_boundary + closing_quote
        ).strip()

        # Ignore a boundary that follows a known abbreviation.
        last_word = before_boundary.split()[-1].lower()

        if last_word in _ABBREVIATIONS:
            continue

        # Look at the beginning of the next sentence.
        remaining = text[match.end():].lstrip()

        next_text = remaining.lstrip(
            "\"'“‘([{"
        )

        if not next_text:
            continue

        # A lowercase continuation is probably not a new
        # sentence. Favor a conservative split.
        if not (
            next_text[0].isupper()
            or next_text[0].isdigit()
        ):
            continue

        if candidate:
            sentences.append(candidate)

        start = match.end()

    final_sentence = text[start:].strip()

    if final_sentence:
        sentences.append(final_sentence)

    return sentences