# Windows packaging change inventory

Existing files modified:

- `app.py`: select Daily through `daily_runtime` rather than importing the Linux SDK directly.
- `tavus_client.py`: use that platform selector; forward meeting tokens; track live
  clients for launcher shutdown; end a newly created room if transport startup fails.
- `local_speech.py`: launch the bundled executable in speech-worker mode when
  frozen, retain the source Python-worker path, and use UTF-8 IPC with a hidden
  worker window on Windows.
- `kokoro_worker.py`: expose the existing worker loop as `main()` for the executable.
- `tests/test_tavus_client.py`: cover cleanup and meeting-token forwarding after a failed join.
- `.gitignore`: exclude downloaded Windows runtimes, build output and generated notices.
- `README.md`: link Windows setup documentation.

New runtime files:

- `daily_runtime.py`: platform selection, with the existing Linux SDK unchanged.
- `windows_daily.py`: isolated Chromium transport and Windows WebRTC VAD.
- `static/windows-daily.js`: Daily JS events, exact Echo submission and remote PCM capture.
- `windows_launcher.py`: credentials UI, local server startup, browser launch and shutdown.
- `windows_diagnostics.py`: explicit, bounded live Tavus check.

New build / verification files:

- `requirements-windows.txt`: direct Windows dependencies.
- `windows/requirements-lock.txt`: resolved build dependency versions.
- `windows/XQ.spec`: PyInstaller asset allowlist and UTF-8 interpreter setting.
- `windows/hooks/hook-webrtcvad.py`: collect the Windows VAD wheel's metadata/binary.
- `windows/assets.json`: public runtime asset hashes.
- `scripts/prepare_windows_assets.py`: pinned Daily SDK and Kokoro downloads.
- `scripts/windows_notices.py`: third-party notices and speech-component sources.
- `scripts/windows_smoke.py`: packaged pages, PIN, scripts, generated speech and shutdown test.
- `scripts/package_windows.py`: clean USB ZIP, readable source, file hashes and integrity check.
- `tests/test_windows_transport.py`: mock browser transport, threading and PCM regression tests.
- `WINDOWS_DISTRIBUTION.md`: recipient instructions and build/architecture notes.
- `windows/CHANGES.md`: this inventory.

No presentation prose, assessment profiles, orchestration rules, playback
trackers, operator PIN, or 15-minute presentation limit were edited.
