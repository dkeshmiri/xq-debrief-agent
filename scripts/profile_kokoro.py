"""Measure uncached CPU synthesis independently of HTTP and browser playback."""
import cProfile
import argparse
import io
import json
import os
from pathlib import Path
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('TMPDIR', str(ROOT / '.cache/tmp'))
from local_speech import KokoroSpeech

speech = KokoroSpeech()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
start = time.perf_counter()
speech._load()
load_seconds = time.perf_counter()-start
profile = cProfile.Profile()
results = []
for text in ['Welcome to XQ.'] + ['Your results are a starting point for understanding, not a box to put someone in.'] * 3:
    start = time.perf_counter()
    profile.enable()
    audio = speech._synthesize_native(text)
    profile.disable()
    import wave
    with wave.open(io.BytesIO(audio)) as wav:
        duration = wav.getnframes()/wav.getframerate()
    results.append(dict(characters=len(text), synthesis_seconds=time.perf_counter()-start, audio_seconds=duration))
report = dict(model_load_seconds=load_seconds, threads=os.getenv('XQ_KOKORO_THREADS', str(min(4, os.cpu_count() or 1))), samples=results)
if args.output:
    args.output.write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report,indent=2))
pstats.Stats(profile).strip_dirs().sort_stats('cumulative').print_stats(12)
