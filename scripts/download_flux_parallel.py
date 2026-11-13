import concurrent.futures as futures
import hashlib
import argparse
import subprocess
import sys
from pathlib import Path
import threading
import time
import requests
from huggingface_hub import model_info, hf_hub_url
from huggingface_hub._local_folder import write_download_metadata

parser = argparse.ArgumentParser(description="Resume and verify the Mac FLUX 3 q4 package.")
parser.add_argument("--workers", type=int, default=16)
args = parser.parse_args()
if not 1 <= args.workers <= 64:
    parser.error("--workers must be between 1 and 64")
PROJECT = Path(__file__).resolve().parent.parent
ROOT = PROJECT / "models/flux3-image-klein-q4"
REPO = 'mflux-community/flux-3-image-klein-mflux-q4'
REV = '79c0034de040c460e9685bf0127f40af042a2abe'
CHUNK = 8 * 1024 * 1024
info = model_info(REPO, revision=REV, files_metadata=True)
files = [s for s in info.siblings if s.lfs]
lock = threading.Lock()
completed = 0

def part_task(task):
    global completed
    file, start, end, part = task
    expected = end - start + 1
    if part.exists() and part.stat().st_size == expected:
        return
    url = hf_hub_url(REPO, file.rfilename, revision=REV)
    for attempt in range(5):
        try:
            with requests.get(url, headers={'Range': f'bytes={start}-{end}'}, stream=True, timeout=(20, 120)) as r:
                if r.status_code != 206 or not r.headers.get('Content-Range', '').startswith(f'bytes {start}-{end}/'):
                    raise RuntimeError(f'Invalid range response: {r.status_code}')
                with part.with_suffix('.tmp').open('wb') as out:
                    for data in r.iter_content(128 * 1024):
                        out.write(data)
            if part.with_suffix('.tmp').stat().st_size != expected:
                raise RuntimeError('Incomplete chunk')
            part.with_suffix('.tmp').replace(part)
            with lock:
                completed += expected
                if completed // CHUNK % 16 == 0:
                    print(f'Fetched {completed // (1024**2)} MiB in verified-length parts', flush=True)
            return
        except Exception as exc:
            if attempt == 4:
                raise RuntimeError(f'Failed chunk {file.rfilename}:{start}, {type(exc).__name__}') from None
            time.sleep(2 ** attempt)

tasks = []
for file in files:
    final = ROOT / file.rfilename
    if final.exists() and final.stat().st_size == file.lfs.size:
        with final.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == file.lfs.sha256:
                continue
    parts = ROOT / '.parts' / file.rfilename
    parts.mkdir(parents=True, exist_ok=True)
    for start in range(0, file.lfs.size, CHUNK):
        tasks.append((file, start, min(start + CHUNK, file.lfs.size) - 1, parts / f'{start:012d}.part'))
remaining = sum(1 for _, start, end, part in tasks if not part.exists() or part.stat().st_size != end-start+1)
print(f"Resuming {remaining} remaining chunks; completed chunks are reused ({args.workers} connections)", flush=True)
with futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
    for _ in executor.map(part_task, tasks):
        pass
for file in files:
    parts = ROOT / '.parts' / file.rfilename
    final = ROOT / file.rfilename
    if final.exists() and final.stat().st_size == file.lfs.size:
        with final.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == file.lfs.sha256:
                continue
    if not parts.exists():
        raise RuntimeError(f"Missing download parts: {file.rfilename}")
    digest = hashlib.sha256()
    with final.with_suffix('.assembling').open('wb') as output:
        for start in range(0, file.lfs.size, CHUNK):
            data = (parts / f'{start:012d}.part').read_bytes()
            digest.update(data)
            output.write(data)
    if digest.hexdigest() != file.lfs.sha256:
        raise RuntimeError(f'Checksum mismatch: {file.rfilename}')
    final.with_suffix('.assembling').replace(final)
    write_download_metadata(ROOT, file.rfilename, REV, file.lfs.sha256)
    for part in parts.glob('*.part'):
        part.unlink()
    print('SHA256 verified:', file.rfilename, flush=True)
print('All large weights downloaded and verified', flush=True)

subprocess.run([sys.executable, str(PROJECT / "scripts/download_flux.py")], check=True)
