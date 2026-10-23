"""Build secret-free Liara source archives from the current working tree."""
import gzip
import json
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "liara"
OUT.mkdir(parents=True, exist_ok=True)
snapshot = OUT / "catalog.sqlite"
with closing(sqlite3.connect(f"file:{ROOT / 'data/torob.sqlite'}?mode=ro", uri=True)) as source, closing(sqlite3.connect(snapshot)) as dest:
    source.backup(dest)
with closing(sqlite3.connect(snapshot)) as dest:
    for table in ("inquiries", "price_checks"):
        dest.execute(f"DELETE FROM {table}")
    dest.commit()
    dest.execute("VACUUM")
    assert dest.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    counts = {t: dest.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("products", "shops", "offers", "inquiries", "price_checks")}
    assert counts["products"] > 0 and counts["inquiries"] == counts["price_checks"] == 0
with snapshot.open("rb") as source, gzip.open(OUT / "catalog.sqlite.gz", "wb", compresslevel=6) as output:
    shutil.copyfileobj(source, output)
snapshot.unlink()

def add_tree(archive, folder, prefix):
    for path in folder.rglob("*"):
        relative = path.relative_to(folder)
        if not path.is_file() or any(p in {"node_modules", ".next", ".git", "__pycache__", "scripts"} for p in relative.parts):
            continue
        if path.name.startswith(".env") or path.suffix in {".log", ".pyc"}:
            continue
        archive.add(path, arcname=str(Path(prefix) / relative), recursive=False)

with tarfile.open(OUT / "app.tgz", "w:gz") as archive:
    archive.add(ROOT / "requirements.txt", arcname="requirements.txt")
    add_tree(archive, ROOT / "src", "src")
    add_tree(archive, ROOT / "prompts", "prompts")
    archive.add(ROOT / "deploy/liara/start.py", arcname="deploy/liara/start.py")
    archive.add(ROOT / "deploy/liara/Dockerfile", arcname="Dockerfile")
    archive.add(OUT / "catalog.sqlite.gz", arcname="seed/catalog.sqlite.gz")
    add_tree(archive, ROOT / "web", "web")
for name in ("app",):
    path = OUT / f"{name}.tgz"
    assert path.stat().st_size < 128 * 1024 ** 2
    with tarfile.open(path) as archive:
        assert not any(".env" == Path(n).name or n.endswith(".sqlite") for n in archive.getnames())
print(json.dumps({"catalog": counts, "archiveBytes": (OUT / "app.tgz").stat().st_size}))
