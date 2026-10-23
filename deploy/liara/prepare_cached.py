"""Package the tested standalone build without another npm installation."""
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/liara"
standalone = ROOT / "web/.next/standalone"
assert (standalone / "server.js").exists(), "Build with NEXT_STANDALONE=1 first."
with tarfile.open(OUT / "app.tgz") as source, tarfile.open(OUT / "cached.tgz", "w:gz") as target:
    for item in source:
        if item.name == "Dockerfile" or item.name.startswith("web/"):
            continue
        target.addfile(item, source.extractfile(item) if item.isfile() else None)
    target.add(ROOT / "deploy/liara/Dockerfile.cached", arcname="Dockerfile")
    for folder, prefix in ((standalone, "web-artifact"), (ROOT / "web/.next/static", "web-artifact/.next/static"), (ROOT / "web/public", "web-artifact/public")):
        for path in folder.rglob("*"):
            if path.is_file():
                assert not path.name.startswith(".env")
                target.add(path, arcname=str(Path(prefix) / path.relative_to(folder)), recursive=False)
assert (OUT / "cached.tgz").stat().st_size < 128 * 1024 ** 2
print("Cached standalone archive:", (OUT / "cached.tgz").stat().st_size, "bytes")
