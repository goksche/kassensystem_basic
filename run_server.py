# run_server.py
import os
import sys
import webbrowser
import threading
import time

def _prepare_workdir_for_pyinstaller():
    """
    Wenn als PyInstaller-EXE gestartet (onefile/onefolder), werden
    die Daten unter _MEIPASS entpackt. Wir wechseln dorthin,
    damit relative Pfade wie 'app/templates' weiterhin funktionieren.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.isdir(base):
        os.chdir(base)

def _open_browser_later(url: str, delay: float = 0.8):
    def _go():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()

def main():
    _prepare_workdir_for_pyinstaller()

    # Jetzt normal starten, ohne deinen Code umzubauen
    import uvicorn
    # Optional: Port/Tuning zentral definieren
    host = "127.0.0.1"
    port = 8000

    # Browser aufrufen, wenn Server gleich ready ist
    _open_browser_later(f"http://{host}:{port}/")

    # Deine bestehende App bleibt unverändert:
    # wir importieren main:app und starten uvicorn
    uvicorn.run("main:app", host=host, port=port, reload=False, log_level="info")

if __name__ == "__main__":
    main()
