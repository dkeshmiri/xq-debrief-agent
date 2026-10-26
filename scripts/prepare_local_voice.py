"""Prepare a saved profile's deterministic narration before a demonstration."""
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from debrief_engine import DebriefEngine
from local_speech import speech
from sentence_splitter import split_sentences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    parser.add_argument('--experience', choices=('family', 'business'), default='family')
    args = parser.parse_args()
    engine = DebriefEngine(args.profile.resolve(), experience=args.experience)
    texts = [engine.get_introduction(), engine.get_disc_narrative(), engine.get_driving_forces_narrative(),
             engine.get_eq_narrative(), engine.get_integrated_narrative(), engine.get_conclusion()]
    sentences = list(dict.fromkeys(sentence for text in texts for sentence in split_sentences(text)))
    start = time.monotonic()
    try:
        speech.ready()
        for index, sentence in enumerate(sentences, 1):
            speech.audio(sentence).result()
            print(f'Prepared {index}/{len(sentences)} clips ({time.monotonic()-start:.0f}s)', flush=True)
    finally:
        speech.close()


if __name__ == '__main__':
    main()
