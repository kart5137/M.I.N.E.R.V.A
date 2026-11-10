from __future__ import annotations

import csv
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


class MalformedExport(ValueError):
    """The downloaded CSV is not a complete, rectangular table."""


def check_csv_structure(path: Path) -> str | None:
    """None when every record has the header's field count; otherwise a description.

    Uses the csv module, which follows quoting rules exactly (WHO comments contain commas
    and line breaks), so a failure means the file itself is broken - typically a
    truncated last record or two records spliced together."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header:
            return "empty file"
        bad = [(n, len(rec)) for n, rec in enumerate(reader, start=2) if len(rec) != len(header)]
    if bad:
        shown = ", ".join(f"record {n}: {k} fields" for n, k in bad[:3])
        return f"{len(bad)} record(s) without {len(header)} fields ({shown})"
    return None


def download_checked(url: str, dest: Path, variants: tuple[dict[str, str], ...], *,
                     label: str) -> Path:
    """Download a CSV export, trying each header variant until one is well formed.

    WHO's xMart exports sit behind a CDN that caches each Accept-Encoding variant
    separately and has served stale, truncated copies. The previous file at `dest` is
    replaced only by a complete download; MalformedExport is raised when none is."""
    tmp = dest.with_name(dest.name + ".download")
    problems = []
    try:
        for headers in variants:
            download(url, tmp, headers=headers)
            problem = check_csv_structure(tmp)
            if problem is None:
                tmp.replace(dest)
                return dest
            log.warning("%s export malformed with %s: %s", label, headers, problem)
            problems.append(f"{headers}: {problem}")
    finally:
        tmp.unlink(missing_ok=True)
    raise MalformedExport(f"Every {label} download was malformed; previous file kept. "
                          + " | ".join(problems))
