"""Build a standalone ZIP and verify checksums and CRC; never invokes Git."""
import hashlib,json,zipfile
from pathlib import Path
from core import ROOT

def main():
    for folder in ROOT.rglob('__pycache__'):
        import shutil
        shutil.rmtree(folder)
    paths=sorted(p for p in ROOT.rglob('*') if p.is_file() and '.venv' not in p.parts and p.name!='SHA256SUMS.txt')
    checks=''.join(f'{hashlib.file_digest(p.open("rb"),"sha256").hexdigest()}  {p.relative_to(ROOT).as_posix()}\n' for p in paths)
    (ROOT/'SHA256SUMS.txt').write_text(checks,encoding='utf-8')
    target=ROOT.parent/'ZooKeeper_HW_ready.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in paths+[ROOT/'SHA256SUMS.txt']:z.write(p,Path(ROOT.name)/p.relative_to(ROOT))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(paths)+1
        for line in checks.splitlines():
            sha,path=line.split('  ',1)
            assert hashlib.sha256(z.read(ROOT.name+'/'+path)).hexdigest()==sha
    assert not (ROOT/'.git').exists()
    print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'files':len(paths)+1,
                      'zip_crc_valid':True,'all_checksums_match':True},ensure_ascii=False))
if __name__=='__main__':main()
