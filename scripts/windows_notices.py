"""Collect third-party notices and speech-component source archives for the ZIP."""
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_windows_assets import download


def main():
    folder = ROOT / 'windows/licenses'
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for distribution in sorted(metadata.distributions(), key=lambda d:d.metadata['Name'].lower()):
        name, version = distribution.metadata['Name'], distribution.version
        rows.append(f'{name} {version}')
        destination = folder / f'{name}-{version}'
        destination.mkdir(exist_ok=True)
        for entry in distribution.files or []:
            path = Path(entry)
            if any(word in path.name.lower() for word in ('license', 'copying', 'notice')) and distribution.locate_file(entry).is_file():
                # Preserve metadata and package paths to avoid duplicate filenames.
                target = destination / str(entry).replace('..', '_parent_')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(distribution.locate_file(entry), target)
    (folder / 'DEPENDENCIES.txt').write_text('\n'.join(rows)+'\n', encoding='utf-8')
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copyfile(python_license, folder / 'Python-LICENSE.txt')
    sources = ROOT / 'windows/component-sources'
    # Source and build recipe for the upstream eSpeak NG 1.52 binary in loader 0.2.4.
    download('https://codeload.github.com/espeak-ng/espeak-ng/tar.gz/refs/tags/1.52.0', sources / 'espeak-ng-1.52.0.tar.gz')
    download('https://codeload.github.com/thewh1teagle/espeakng-loader/tar.gz/e5e9200dc3fd894b7415942c2602fc31526d60fc',
             sources / 'espeakng-loader-build-source.tar.gz')
    # Exact installed loader wrapper, including source; library sources are above.
    import espeakng_loader
    shutil.copyfile(Path(espeakng_loader.__file__), sources / 'espeakng_loader-0.2.4.py')
    for name in ('phonemizer', 'kokoro-onnx'):
        version = metadata.version(name)
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=30) as response:
            record = json.load(response)
        for entry in record['urls']:
            if entry['packagetype'] == 'sdist':
                download(entry['url'], sources / entry['filename'], entry['digests']['sha256'])
                break
        else:
            # The pure-Python wheel is source-bearing when no sdist is published.
            entry = next(e for e in record['urls'] if e['filename'].endswith('py3-none-any.whl'))
            download(entry['url'], sources / entry['filename'], entry['digests']['sha256'])
    print('Third-party notices and speech sources collected.')


if __name__ == '__main__':
    main()
