"""Native Windows launcher; credentials stay in this user's LocalAppData.

The launcher starts one server child, opens the normal browser only after the
server reports ready, and requests graceful shutdown over private stdin.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def configure_runtime():
    os.chdir(ROOT)
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'browsers')
    if not getattr(sys, 'frozen', False):
        os.environ.setdefault('XQ_KOKORO_PYTHON', sys.executable)
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')


def serve():
    from threading import Event, Thread
    from waitress import create_server
    import app
    from tavus_client import TavusClient
    from local_speech import speech
    stopping = Event()
    server = create_server(app.app, host='127.0.0.1', port=0, threads=8)

    def shutdown():
        if stopping.is_set():
            return
        stopping.set()
        app.background_stop.set()
        # No playback lock is held while waiting for network callbacks.
        for client in list(TavusClient.instances):
            try:
                if client.conversation_id:
                    client.end_conversation()
            except Exception:
                print('A Tavus session could not be ended remotely; check the Tavus dashboard.', flush=True)
            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass
        speech.close()
        server.close()

    def watch_parent():
        for line in sys.stdin:
            if line.strip() == 'stop':
                break
        shutdown()

    Thread(target=watch_parent, daemon=True, name='xq-launcher-control').start()
    print(f'XQ_READY=http://127.0.0.1:{server.effective_port}', flush=True)
    try:
        server.run()
    finally:
        shutdown()


def gui():
    import ctypes
    import hashlib
    import queue
    import subprocess
    import threading
    import time
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox, ttk
    from dotenv import dotenv_values, set_key

    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\XQ-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:20])
    if kernel.GetLastError() == 183:
        messagebox.showinfo('XQ', 'XQ is already open. Use its existing launcher window.')
        return
    # This console build also serves the worker IPC. Hide only the GUI console.
    window = kernel.GetConsoleWindow()
    if window:
        ctypes.windll.user32.ShowWindow(window, 0)

    home = Path(os.environ['LOCALAPPDATA']) / 'XQDesktop'
    home.mkdir(parents=True, exist_ok=True)
    settings = home / 'settings.env'
    saved = dotenv_values(settings) if settings.exists() else {}
    root = tk.Tk()
    root.title('XQ — Family & Workplace')
    root.geometry('620x465')
    root.minsize(620, 465)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='XQ', font=('Segoe UI', 24, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Family, Workplace and Presentation Mode', font=('Segoe UI', 12)).pack(anchor='w', pady=(0,16))
    fields = {}
    for key, label in [('OPENAI_API_KEY','OpenAI API key'), ('TAVUS_API_KEY','Tavus API key'),
                       ('TAVUS_PAL_ID','Tavus PAL ID'), ('XQ_PRESENTATION_TAVUS_PAL_ID','Presentation PAL ID (optional)')]:
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=3)
        ttk.Label(row, text=label, width=31).pack(side='left')
        value = tk.StringVar(value=saved.get(key) or '')
        ttk.Entry(row, textvariable=value, show='*' if key.endswith('API_KEY') else '').pack(side='left', fill='x', expand=True)
        fields[key] = value
    provider = tk.StringVar(value=saved.get('XQ_PLAYBACK_PROVIDER') or 'kokoro')
    row = ttk.Frame(frame)
    row.pack(fill='x', pady=10)
    ttk.Label(row, text='Family / Workplace voice', width=31).pack(side='left')
    ttk.Combobox(row, textvariable=provider, values=['kokoro','tavus'], state='readonly', width=17).pack(side='left')
    ttk.Label(frame, text='kokoro = local robot voice. Presentation Mode uses Tavus.\nSettings are saved on this PC, outside the USB package.', wraplength=560).pack(anchor='w')
    status = tk.StringVar(value='Enter your keys, then start XQ.')
    ttk.Label(frame, textvariable=status, wraplength=560).pack(anchor='w', pady=14)
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x')
    process = None
    messages = queue.Queue()
    address = None
    closing = False
    deadline = None

    def read_output(child):
        with (home / 'launcher.log').open('w', encoding='utf-8') as log:
            for line in child.stdout:
                log.write(line)
                log.flush()
                if line.startswith('XQ_READY='):
                    messages.put(line.strip().split('=', 1)[1])

    def start():
        nonlocal process, address, deadline
        if process is not None and process.poll() is None:
            return
        values = {key:value.get().strip() for key,value in fields.items()}
        if not values['OPENAI_API_KEY']:
            messagebox.showerror('XQ setup', 'Enter an OpenAI API key for questions and transcription.')
            return
        if provider.get() == 'tavus' and not all(values[key] for key in ('TAVUS_API_KEY','TAVUS_PAL_ID')):
            messagebox.showerror('XQ setup', 'Tavus voice requires a Tavus API key and PAL ID.')
            return
        try:
            values['XQ_PLAYBACK_PROVIDER'] = provider.get()
            for key,value in values.items():
                set_key(str(settings), key, value)
            probe = ROOT / '.xq-write-check'
            probe.write_text('')
            probe.unlink()
            command = [sys.executable, '--serve'] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__)), '--serve']
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                                       creationflags=subprocess.CREATE_NO_WINDOW,
                                       env={**os.environ, **values})
            threading.Thread(target=read_output, args=(process,), daemon=True).start()
            address = None
            deadline = None
            start_button.config(state='disabled')
            stop_button.config(state='normal')
            status.set('Starting XQ…')
        except Exception as error:
            messagebox.showerror('XQ could not start', f'{error}\nCopy the entire package to a writable local folder first.')

    def stop():
        nonlocal deadline
        if process is not None and process.poll() is None and deadline is None:
            try:
                process.stdin.write('stop\n')
                process.stdin.flush()
            except OSError:
                pass
            deadline = time.monotonic() + 90
            status.set('Ending sessions and shutting down…')
            stop_button.config(state='disabled')

    def close():
        nonlocal closing
        closing = True
        stop()
        if process is None or process.poll() is not None:
            root.destroy()

    def poll():
        nonlocal process, address, deadline
        try:
            url = messages.get_nowait()
            if deadline is None and not closing:
                address = url
                status.set('XQ is running. Keep this window open. Stop XQ here when finished.')
                webbrowser.open(address)
        except queue.Empty:
            pass
        if process is not None and process.poll() is not None:
            code = process.returncode
            process = None
            deadline = None
            address = None
            start_button.config(state='normal')
            stop_button.config(state='disabled')
            status.set('XQ stopped.' if code == 0 else f'XQ stopped with an error. See {home / "launcher.log"}')
            if closing:
                root.destroy()
                return
        if deadline is not None and time.monotonic() > deadline:
            status.set('Shutdown is taking longer than expected. Check launcher.log; close any active Tavus session in its dashboard.')
        root.after(250, poll)

    start_button = ttk.Button(buttons, text='Start XQ', command=start)
    start_button.pack(side='left')
    ttk.Button(buttons, text='Open browser', command=lambda: webbrowser.open(address) if address else None).pack(side='left', padx=8)
    stop_button = ttk.Button(buttons, text='Stop XQ', command=stop, state='disabled')
    stop_button.pack(side='left')
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(250, poll)
    root.mainloop()
    kernel.CloseHandle(ctypes.c_void_p(mutex))


if __name__ == '__main__':
    configure_runtime()
    if '--kokoro-worker' in sys.argv:
        from kokoro_worker import main
        main()
    elif '--serve' in sys.argv:
        serve()
    elif '--check-tavus' in sys.argv:
        from windows_diagnostics import tavus_check
        tavus_check()
    else:
        gui()
