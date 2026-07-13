import ctypes
import re
import subprocess
import tempfile
from pathlib import Path


def admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def port_status(port):
    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True, errors="ignore")
    except Exception:
        return "verifica porta non disponibile"
    pids = []
    pat = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+\S+\s+(\d+)\s*$", re.I)
    for line in out.splitlines():
        m = pat.match(line)
        if m:
            pids.append(m.group(1))
    pids = sorted(set(pids))
    return f"occupata, PID: {', '.join(pids)}" if pids else "libera"


def rw_ok():
    cwd = Path.cwd()
    try:
        list(cwd.iterdir())
        r = True
    except Exception:
        r = False
    with tempfile.NamedTemporaryFile(prefix=".diag_", delete=False, dir=cwd) as t:
        f = Path(t.name)
    try:
        f.write_text("x", encoding="utf-8")
        w = True
    except Exception:
        w = False
    finally:
        try:
            f.unlink()
        except Exception:
            pass
    return r, w


if __name__ == "__main__":
    r, w = rw_ok()
    print(f"Amministratore: {'SI' if admin() else 'NO'}")
    print(f"Porta 80: {port_status(80)}")
    print(f"Porta 3306: {port_status(3306)}")
    print(f"Cartella progetto: lettura={'SI' if r else 'NO'}, scrittura={'SI' if w else 'NO'}")
