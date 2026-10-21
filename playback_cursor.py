
from dataclasses import dataclass

from debrief_state import DebriefState


@dataclass(frozen=True)
class Utterance:
    """One sentence scheduled for playback."""

    id: int
    section: DebriefState
    sentence_index: int
    text: str


class PlaybackCursor:
    """
    Tracks narration at sentence level.

    It does not split text, play audio, call GPT,
    or control Tavus. Those belong to other modules.
    """

    def __init__(self) -> None:
        self.section: DebriefState | None = None
        self.sentences: tuple[str, ...] = ()
        self.sentence_index = 0
        self.paused = False

        self.active_utterance: Utterance | None = None
        self._next_id = 0

    def load_section(
        self,
        section: DebriefState,
        sentences: list[str],
    ) -> None:
        """Load a section and begin at its first sentence."""

        if self.active_utterance is not None:
            raise RuntimeError(
                "Cannot load a section while an utterance "
                "is active. Interrupt it first."
            )

        cleaned = tuple(
            sentence.strip()
            for sentence in sentences
            if sentence.strip()
        )

        if not cleaned:
            raise ValueError(
                "A section must contain at least one sentence."
            )

        self.section = section
        self.sentences = cleaned
        self.sentence_index = 0
        self.paused = False

    def start_next(self) -> Utterance | None:
        """
        Schedule the current sentence.

        The cursor does not advance until complete()
        receives confirmation for this utterance.
        """

        if self.section is None or self.paused:
            return None

        if self.active_utterance is not None:
            return None

        if self.sentence_index >= len(self.sentences):
            return None

        self._next_id += 1

        utterance = Utterance(
            id=self._next_id,
            section=self.section,
            sentence_index=self.sentence_index,
            text=self.sentences[self.sentence_index],
        )

        self.active_utterance = utterance
        return utterance

    def complete(self, utterance_id: int) -> bool:
        """
        Advance only when the active utterance
        is confirmed to have finished.
        """

        if self.paused or self.active_utterance is None:
            return False

        if self.active_utterance.id != utterance_id:
            return False

        self.active_utterance = None
        self.sentence_index += 1
        return True

    def interrupt(self) -> None:
        """
        Pause without advancing.

        Invalidating the active utterance also makes
        a late completion event harmless.
        """

        self.paused = True
        self.active_utterance = None

    def resume(self) -> Utterance | None:
        """Restart the interrupted sentence from its beginning."""

        self.paused = False
        return self.start_next()

    @property
    def finished(self) -> bool:
        """Whether every sentence in the loaded section is complete."""

        return (
            self.section is not None
            and self.sentence_index >= len(self.sentences)
            and self.active_utterance is None
        )