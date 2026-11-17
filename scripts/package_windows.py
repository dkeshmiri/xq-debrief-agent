"""Make the clean USB ZIP from a tested build, excluding runtime state and keys."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {'.git', '.env', '.cache', '__pycache__', 'assessment_drafts'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist/XQ')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    dist = args.dist.resolve()
    if not (dist / 'XQ.exe').is_file():
        raise SystemExit('Build XQ.exe first.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    names = set()
    with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        def add(path, relative):
            name = 'XQ/' + relative.as_posix()
            if name in names:
                return
            data = path.read_bytes()
            archive.writestr(name, data)
            names.add(name)
            hashes[name] = hashlib.sha256(data).hexdigest()
        for path in sorted(dist.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(dist)
            if PRIVATE_PARTS.intersection(relative.parts) or relative.parts[:3] == ('_internal','data','business'):
                continue
            add(path, relative)
        for source, dest in [('WINDOWS_DISTRIBUTION.md','START-HERE.md'),
                             ('windows/CHANGES.md','SOURCE-CHANGES.md'),
                             ('windows/requirements-lock.txt','requirements-lock.txt'),
                             ('windows/assets.json','assets.json')]:
            add(ROOT / source, Path(dest))
        for path in sorted((ROOT / 'windows/component-sources').rglob('*')):
            if path.is_file():
                add(path, Path('component-sources') / path.relative_to(ROOT / 'windows/component-sources'))
        # Human-readable application source for inspection and rebuilding.
        for path in sorted(ROOT.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if PRIVATE_PARTS.intersection(relative.parts):
                continue
            allowed = (len(relative.parts) == 1 and path.suffix in ('.py','.txt','.md')) or relative.parts[0] in {
                'templates','static','knowledge','narratives','tests','scripts'}
            allowed |= relative.parts[:2] in {('content','business'), ('content','presentations'),
                                             ('data','families'), ('data','personas')}
            allowed |= relative.as_posix() in {'content/presentation.json','content/presentation_profile.json',
                                              'windows/XQ.spec','windows/hooks/hook-webrtcvad.py'}
            if allowed:
                add(path, Path('source') / relative)
        archive.writestr('XQ/BUILD-INFO.json', json.dumps({
            'built_at_utc':datetime.now(timezone.utc).isoformat(),
            'platform':'Windows x64', 'files_sha256':hashes,
            'note':'Unsigned local build. API credentials and runtime session data excluded.',
        }, indent=2))
    with zipfile.ZipFile(args.output) as archive:
        invalid = archive.testzip()
        if invalid:
            raise RuntimeError('ZIP integrity failed: ' + invalid)
        for name in archive.namelist():
            if PRIVATE_PARTS.intersection(Path(name).parts):
                raise RuntimeError('Private runtime file included: ' + name)
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix('.zip.sha256').write_text(f'{checksum}  {args.output.name}\n', encoding='ascii')
    print(f'Created {args.output} ({args.output.stat().st_size / 1024**2:.1f} MiB); ZIP integrity verified.')


if __name__ == '__main__':
    main()
