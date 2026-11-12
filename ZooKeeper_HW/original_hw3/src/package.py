import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = [
        path
        for path in sorted(ROOT.rglob("*"))
        if path.is_file()
        and not any(x in path.parts for x in (".cache", "__pycache__", ".venv"))
        and path.name not in ("SHA256SUMS.txt", ".DS_Store", ".env")
    ]
    lines = []
    for path in paths:
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        lines.append(digest + "  " + path.relative_to(ROOT).as_posix())
    manifest = ROOT / "SHA256SUMS.txt"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths.append(manifest)
    target = ROOT.parent / "Homework3_PHP.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in paths:
            archive.write(path, arcname=str(Path(ROOT.name) / path.relative_to(ROOT)))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert sum(path.endswith(".pdf") for path in archive.namelist()) == 1
    print(
        json.dumps(
            {"zip": str(target), "bytes": target.stat().st_size, "files": len(paths)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
