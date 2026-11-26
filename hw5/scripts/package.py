#!/usr/bin/env python3
"""Package deliverables and verify ZIP CRC; no Git operations."""
import hashlib,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SKIP={'.local','.kubectl-cache','__pycache__','.git','.venv'}
files=sorted(p for p in ROOT.rglob('*') if p.is_file() and not SKIP.intersection(p.relative_to(ROOT).parts) and p.name!='SHA256SUMS.txt')
checks=ROOT/'SHA256SUMS.txt';checks.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(ROOT))+'\n' for p in files))
archive=ROOT.with_suffix('.zip')
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in files+[checks]:z.write(p,str(Path(ROOT.name)/p.relative_to(ROOT)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(archive)
print(f'{len(files)+1} files, {archive.stat().st_size:,} bytes, CRC verified')
