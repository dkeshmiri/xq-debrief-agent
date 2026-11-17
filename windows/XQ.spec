# Build with: python -m PyInstaller windows/XQ.spec --noconfirm
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas = [(str(root / name), name) for name in ('templates', 'static', 'knowledge', 'narratives', 'models', 'browsers')]
# App data is explicitly selected. Never bundle .env, drafts, imported business
# profiles, transcript-source archives, speech caches, Git or a developer venv.
datas += [(str(root / 'data/families'), 'data/families'),
          (str(root / 'data/personas'), 'data/personas'),
          (str(root / 'content/business'), 'content/business'),
          (str(root / 'content/presentations'), 'content/presentations'),
          (str(root / 'content/presentation.json'), 'content'),
          (str(root / 'content/presentation_profile.json'), 'content'),
          (str(root / 'app.py'), '.'),
          (str(root / 'windows/licenses'), 'licenses')]
binaries = []
# Preserve the build interpreter's certificate policy when it has extra CA data.
certificate_policy = Path(sys.base_prefix) / 'Lib/codex-rejected-cas.pem'
if certificate_policy.exists():
    datas.append((str(certificate_policy), '.'))
hiddenimports = [p.stem for p in root.glob('*.py') if not p.stem.startswith(('echo_test', 'main', 'windows_launcher'))]
for package in ('kokoro_onnx', 'onnxruntime', 'espeakng_loader', 'phonemizer'):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
a = Analysis([str(root / 'windows_launcher.py')], pathex=[str(root)],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             hookspath=[str(root / 'windows/hooks')],
             excludes=['daily'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [('X utf8', None, 'OPTION')], exclude_binaries=True, name='XQ',
          debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='XQ')
