"""Seed a new persistent volume once, then run the API as the app user."""
import gzip
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

def seed(target, archive):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(".seeding")
        with gzip.open(archive, "rb") as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
        temporary.replace(target)

def main():
    target = Path(os.environ.get("DB_PATH", "/app/data/torob.sqlite"))
    seed(target, "/app/seed/catalog.sqlite.gz")
    if os.getuid() == 0:
        os.chown(target.parent, 10001, 10001)
        for item in target.parent.iterdir():
            if item.is_file():
                os.chown(item, 10001, 10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    children = []
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    try:
        children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "src.api:app", "--host", "127.0.0.1", "--port", "8000", "--proxy-headers"]))
        children.append(subprocess.Popen(["node", "server.js"], cwd="/app/web", env={**os.environ, "PORT": "3000", "HOSTNAME": "0.0.0.0"}))
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise SystemExit(1)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

if __name__ == "__main__":
    main()
