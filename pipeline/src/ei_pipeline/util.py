from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import requests

from ei_pipeline.config import USER_AGENT

log = logging.getLogger(__name__)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, *, timeout: int = 600, retries: int = 3,
             headers: dict[str, str] | None = None) -> Path:
    """Stream `url` to `dest` atomically (temp file + rename), retrying transient errors."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            with requests.get(
                url, stream=True, timeout=timeout,
                headers={"User-Agent": USER_AGENT, **(headers or {})}
            ) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
            tmp.replace(dest)
            return dest
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            wait = 2**attempt
            log.warning("Download failed (%s), retrying in %ss: %s", url, wait, exc)
            time.sleep(wait)
    raise AssertionError("unreachable")
