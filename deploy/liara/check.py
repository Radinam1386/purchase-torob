"""Run with Python: verify first-boot seeding cannot overwrite persisted data."""
import gzip
from pathlib import Path
import tempfile
import tarfile

from start import seed

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    archive, target = folder / "catalog.gz", folder / "data/catalog.sqlite"
    with gzip.open(archive, "wb") as stream:
        stream.write(b"catalog fixture")
    seed(target, archive)
    assert target.read_bytes() == b"catalog fixture"
    target.write_bytes(b"persisted user records")
    seed(target, archive)
    assert target.read_bytes() == b"persisted user records"
    broken = folder / "broken.gz"
    broken.write_bytes(b"not gzip")
    missing = folder / "data/missing.sqlite"
    try:
        seed(missing, broken)
    except gzip.BadGzipFile:
        pass
    else:
        raise AssertionError("Invalid seed must fail.")
    assert not missing.exists()
print("PASS first boot, persisted records preserved, invalid seed rejected")

cached = Path(__file__).resolve().parents[2] / "output/liara/cached.tgz"
if cached.exists():
    with tarfile.open(cached) as archive:
        members = archive.getmembers()
        assert not any(item.issym() or item.islnk() for item in members)
        assert all(not Path(item.name).is_absolute() and ".." not in Path(item.name).parts and "\\" not in item.name for item in members)
        names = {item.name for item in members}
        assert {"Dockerfile", "web-artifact/server.js", "web-artifact/node_modules/next/package.json", "seed/catalog.sqlite.gz"} <= names
    print("PASS cached runtime archive paths, files and no symlinks")
