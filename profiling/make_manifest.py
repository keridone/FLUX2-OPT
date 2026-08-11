import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


root = Path(__file__).resolve().parent
artifacts = []
for path in sorted((root / "results").rglob("*")):
    if path.is_file() and path.name != "MANIFEST.json" and path.suffix not in {".png", ".log"}:
        artifacts.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
(root / "results" / "MANIFEST.json").write_text(
    json.dumps({"artifact_count": len(artifacts), "artifacts": artifacts}, indent=2),
    encoding="utf-8",
)
