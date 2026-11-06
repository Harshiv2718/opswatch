#!/usr/bin/env python
"""Download the official full BGL archive and verify its published MD5."""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

URL = "https://zenodo.org/records/8196385/files/BGL.zip?download=1"
MD5 = "4452953c470f2d95fcb32d5f6e733f7a"
MAX_BYTES = 100 * 1024 * 1024


def download(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")
    digest = hashlib.md5()
    size = 0
    try:
        with urllib.request.urlopen(URL, timeout=60) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Download exceeded the expected archive size bound.")
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest() != MD5:
            raise ValueError(f"Archive checksum mismatch: expected {MD5}, got {digest.hexdigest()}.")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"url": URL, "path": str(output), "bytes": size, "md5": digest.hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/BGL.zip"))
    args = parser.parse_args()
    try:
        print(download(args.output))
    except (ValueError, OSError) as exc:
        sys.exit(f"Download failed: {exc}")
