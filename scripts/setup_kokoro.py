"""Run with Python 3.12 or 3.13 to install the isolated local speech runtime."""
import hashlib
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

ROOT = Path(__file__).resolve().parents[1]
RELEASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'
ASSETS = {
    'kokoro-v1.0.onnx': 'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
    'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}


def main():
    if sys.version_info[:2] not in ((3, 12), (3, 13)):
        raise SystemExit('Run this setup with Python 3.12 or 3.13. The main app environment is unchanged.')
    runtime = ROOT / '.venv-kokoro'
    venv.create(runtime, with_pip=True)
    python = runtime / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements-kokoro.txt')], check=True)
    folder = ROOT / 'models/kokoro'
    folder.mkdir(parents=True, exist_ok=True)
    for name, expected in ASSETS.items():
        target = folder / name
        if not target.exists():
            temporary = target.with_suffix('.download')
            print('Downloading', name, flush=True)
            urllib.request.urlretrieve(RELEASE + name, temporary)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise SystemExit(f'Checksum mismatch for {name}; incomplete download was not installed.')
            temporary.replace(target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise SystemExit(f'Checksum mismatch for existing {name}; inspect or remove it before retrying.')
        print(name, 'verified')
    print('Local speech is installed. Start the app normally.')


if __name__ == '__main__':
    main()
