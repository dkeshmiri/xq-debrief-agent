# Native Windows distribution

The Windows package contains XQ.exe, Python, a headless Chromium transport,
Kokoro's model/voices, and the app's current profiles and presentations. No WSL,
Python installation, API keys, developer environment, saved business imports,
assessment drafts, or generated speech caches are included.

## Using a USB copy

1. Copy the entire XQ folder from USB into a writable folder on the PC. Do not
   move XQ.exe away from its _internal folder. Windows x64 is required.
2. Run XQ.exe. Enter the recipient's OpenAI API key. For Tavus presentations or
   debriefs, also enter the Tavus API key and PAL ID. A separate presentation PAL
   ID is optional. The launcher saves these settings on this PC at
   %LOCALAPPDATA%\XQDesktop\settings.env; this file is not encrypted.
3. Leave kokoro selected for the current local robot debrief, or choose tavus
   for the avatar. Click Start XQ; the browser opens automatically.
4. Presentation Mode retains Operator PIN 2020 and its 15-minute limit.
   The Persian presentation remains human-led, as in the existing app.
5. Click Stop XQ in the launcher when finished. Keep the launcher open while
   using the app. Closing only the browser does not end the server.

The package contains the repository's saved household profiles and Amethyst's
script. Distribute it only to the intended recipients. New imports and speech
caches remain in that copy's _internal folder. Distribute the original clean ZIP,
not a folder used for private sessions. Cloud reasoning, transcription and Tavus
still require internet and the corresponding service accounts.

The executable is unsigned. Windows may show an unknown-publisher prompt. No
firewall exception is needed for the loopback web server; Tavus still needs its
normal outbound HTTPS/WebRTC network access. Diagnostics are in
%LOCALAPPDATA%\XQDesktop\launcher.log.

## Build on Windows (Python 3.12 x64)

Use a clean checkout. Keep build tools out of the development venv:

```powershell
py -3.12 -m venv .venv-windows
.venv-windows\Scripts\python -m pip install -r requirements-windows.txt
.venv-windows\Scripts\python scripts/prepare_windows_assets.py
.venv-windows\Scripts\python scripts/windows_notices.py
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\browsers"
.venv-windows\Scripts\python -m playwright install chromium --only-shell
.venv-windows\Scripts\python -m PyInstaller windows/XQ.spec --noconfirm
.venv-windows\Scripts\python scripts/package_windows.py --output dist/XQ-Windows-x64.zip
```

The packaging script includes these instructions, component sources and readable
application source, and excludes generated caches and session data. Distribute
the resulting clean ZIP. Assets are versioned in scripts/prepare_windows_assets.py;
models have fixed SHA-256 checksums and windows/assets.json records downloads.
windows/requirements-lock.txt records the exact resolved dependency versions for
this build. For source runs on Windows, use `python -X utf8 windows_launcher.py`.

Run `python -X utf8 scripts/windows_smoke.py --exe dist/XQ/XQ.exe` to test a
package with dummy credentials and no paid services. `XQ.exe --check-tavus` is
an explicit live diagnostic: supply Tavus credentials in its environment; it
creates one session capped at 120 seconds, speaks one sentence and ends it.

## Implementation boundary

- daily_runtime.py selects the existing native Daily SDK on Linux and
  windows_daily.py on Windows.
- windows_daily.py and static/windows-daily.js join a separate, receive-only
  Daily JS call in bundled headless Chromium. Echo and interrupt messages retain
  the existing Tavus schema. Canonical events enter the unchanged playback
  trackers. Only selected remote user microphones are subscribed, at 16 kHz mono.
- Windows uses WebRTC VAD through webrtcvad-wheels. Existing segmentation and
  question routing remain in place. Linux keeps Daily's VAD.
- Browser callbacks run on a separate thread from Chromium, preserving the
  playback-lock boundary. Generation checks still reject old call callbacks.
- windows_launcher.py starts one Waitress process, bound to 127.0.0.1 on an
  available port, opens the browser after startup, and shuts down sessions through
  a private stdin pipe. API keys never enter the headless browser.
- local_speech.py reuses XQ.exe in worker mode in a frozen build. The source
  deployment keeps its existing separate Python worker.

Automated smoke tests do not prove that a recipient's network can reach Tavus.
Validate a short live presentation on the target network before an investor demo.
