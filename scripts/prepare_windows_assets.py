"""Download pinned public runtime assets, never developer credentials or caches."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODEL_BASE = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'
MODELS = {
    'kokoro-v1.0.onnx':'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
    'voices-v1.0.bin':'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}


def download(url, target, checksum=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + '.download')
        print('Downloading', target.name, flush=True)
        urllib.request.urlretrieve(url, temporary)
        temporary.replace(target)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if checksum and actual != checksum:
        raise RuntimeError(f'Checksum mismatch for {target}; remove it and rerun.')
    return actual


def main():
    manifest = {}
    for name, checksum in MODELS.items():
        manifest[name] = download(MODEL_BASE + name, ROOT / 'models/kokoro' / name, checksum)
    manifest['daily.js'] = download('https://unpkg.com/@daily-co/daily-js@0.94.0/dist/daily-iframe.js',
                                    ROOT / 'static/vendor/daily.js',
                                    'ada1c226e006828210160e97ccfe0862f7fb974b42300c3cae4a2a0ae3a36bca')
    licenses = ROOT / 'windows/licenses'
    download('https://unpkg.com/@daily-co/daily-js@0.94.0/LICENSE', licenses / 'Daily-JS-LICENSE.txt')
    download('https://www.apache.org/licenses/LICENSE-2.0.txt', licenses / 'Kokoro-model-LICENSE.txt')
    download('https://huggingface.co/hexgrad/Kokoro-82M/raw/main/README.md', licenses / 'Kokoro-model-card.txt')
    (ROOT / 'windows/assets.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print('Windows assets ready.', flush=True)


if __name__ == '__main__':
    main()
