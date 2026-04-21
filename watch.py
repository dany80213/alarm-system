#!/usr/bin/env python3
"""
Watcher daemon: riavvia automaticamente il server quando i file cambiano.
Uso: python watch.py
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

ROOT      = Path(__file__).parent
PYTHON    = sys.executable
SERVER_CMD = [PYTHON, "main.py", "--api", "--no-cli"]
LOG_FILE  = ROOT / "logs" / "server.log"

# Estensioni e cartelle monitorate
WATCH_EXTS = {".py", ".json", ".html", ".js", ".css"}
WATCH_DIRS = [ROOT / "api", ROOT / "core", ROOT / "web", ROOT / "config", ROOT]
IGNORE_DIRS = {"__pycache__", ".git", "logs", "simulator"}

# ─── Colori ANSI ─────────────────────────────────────────────────────────────
GRN  = "\033[92m"
YLW  = "\033[93m"
RED  = "\033[91m"
CYAN = "\033[96m"
RST  = "\033[0m"

def log(msg, color=CYAN):
    ts = time.strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{RST}", flush=True)


# ─── Snapshot dei file ────────────────────────────────────────────────────────

def _snapshot():
    """Restituisce {path: mtime} per tutti i file monitorati."""
    snap = {}
    for watch_dir in WATCH_DIRS:
        if not watch_dir.is_dir():
            continue
        depth = 0 if watch_dir == ROOT else 10
        for root, dirs, files in os.walk(watch_dir):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            # Nella root monitoriamo solo i file diretti (non le sottocartelle,
            # quelle le gestiscono i WATCH_DIRS specifici)
            if Path(root) == ROOT and depth == 0:
                dirs.clear()
            for fname in files:
                if Path(fname).suffix in WATCH_EXTS:
                    p = Path(root) / fname
                    try:
                        snap[str(p)] = p.stat().st_mtime
                    except OSError:
                        pass
    return snap


# ─── Gestione processo server ─────────────────────────────────────────────────

server_proc = None
_lock = threading.Lock()

def start_server():
    global server_proc
    LOG_FILE.parent.mkdir(exist_ok=True)
    log_fd = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        SERVER_CMD,
        cwd=str(ROOT),
        stdout=log_fd,
        stderr=log_fd,
        preexec_fn=os.setsid,   # nuovo gruppo di processi
    )
    server_proc = proc
    log(f"Server avviato  PID {proc.pid}", GRN)
    return proc

def stop_server():
    global server_proc
    if server_proc and server_proc.poll() is None:
        pid = server_proc.pid
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            server_proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                pass
        log(f"Server fermato  PID {pid}", YLW)
    server_proc = None

def restart_server(reason=""):
    with _lock:
        if reason:
            log(f"Modifica rilevata: {reason}", YLW)
        stop_server()
        time.sleep(0.5)
        start_server()


# ─── Loop di watch ────────────────────────────────────────────────────────────

def watch_loop():
    snap = _snapshot()
    log(f"Monitorando {len(snap)} file — in attesa di modifiche...", CYAN)

    DEBOUNCE  = 1.0    # secondi di attesa dopo la prima modifica
    pending   = False
    changed   = ""
    last_seen = 0.0

    while True:
        time.sleep(0.5)
        now   = time.time()
        new   = _snapshot()

        diff = None
        for path, mtime in new.items():
            if snap.get(path) != mtime:
                diff = path
                break
        for path in snap:
            if path not in new:
                diff = path
                break

        if diff:
            pending   = True
            changed   = Path(diff).name
            last_seen = now
            snap      = new

        if pending and (now - last_seen) >= DEBOUNCE:
            pending = False
            restart_server(changed)
            snap = _snapshot()


# ─── Gestione segnali ─────────────────────────────────────────────────────────

def _shutdown(sig, frame):
    print()
    log("Arresto watcher...", YLW)
    stop_server()
    sys.exit(0)

signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{CYAN}═══════════════════════════════════════{RST}")
    print(f"{GRN}  Alarm System — Auto-restart Watcher{RST}")
    print(f"{CYAN}═══════════════════════════════════════{RST}\n")
    log(f"Python:  {PYTHON}")
    log(f"Log:     {LOG_FILE}")
    log(f"Estensioni: {', '.join(sorted(WATCH_EXTS))}")
    print()

    start_server()
    time.sleep(1.5)
    watch_loop()
