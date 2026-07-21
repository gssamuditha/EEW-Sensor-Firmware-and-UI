"""
retention.py — miniSEED Archive Retention Policy
=================================================
Deletes miniSEED files older than `retention_days` from the SDS archive to
prevent the SD card from filling up.

Strategy
--------
    * Walk the SDS archive directory tree.
    * Parse year + Julian day from each filename (NET.STA.LOC.CHAN.D.YYYY.JDAY).
    * Delete files whose day is strictly older than today - retention_days.
    * Remove any directories that become empty after deletion.

This module is intentionally standalone — it can be called both from the
FastAPI lifespan background task and from the standalone cron script.
"""

import os
import sys
import time
from pathlib import Path

try:
    from obspy import UTCDateTime
    OBSPY_AVAILABLE = True
except ImportError:
    OBSPY_AVAILABLE = False


def delete_old_mseed_files(archive_root: str, retention_days: int) -> dict:
    """
    Delete miniSEED files older than retention_days from the SDS archive.

    Parameters
    ----------
    archive_root    : Absolute path to the SDS archive root directory.
    retention_days  : Number of days to retain. Files older than this are deleted.

    Returns
    -------
    dict with keys:
        deleted_files : int — number of files deleted
        freed_bytes   : int — approximate bytes freed
        errors        : list[str] — any file deletion errors
    """
    if not os.path.isdir(archive_root):
        return {'deleted_files': 0, 'freed_bytes': 0, 'errors': []}

    # Cutoff as Julian day bookkeeping
    if OBSPY_AVAILABLE:
        cutoff = UTCDateTime() - (retention_days * 86400)
        cutoff_year = cutoff.year
        cutoff_jday = cutoff.julday
    else:
        import datetime
        cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
        cutoff_year = cutoff_dt.year
        cutoff_jday = cutoff_dt.timetuple().tm_yday

    deleted_files = 0
    freed_bytes   = 0
    errors        = []
    dirs_to_check = set()

    for dirpath, _dirs, filenames in os.walk(archive_root, topdown=False):
        for fname in filenames:
            # Expected: NET.STA.LOC.CHAN.D.YYYY.JDAY
            parts = fname.split('.')
            if len(parts) < 7:
                continue
            try:
                file_year = int(parts[5])
                file_jday = int(parts[6])
            except (ValueError, IndexError):
                continue

            # File is older if its year is less, or same year but earlier Julian day
            is_old = (
                file_year < cutoff_year or
                (file_year == cutoff_year and file_jday < cutoff_jday)
            )

            if is_old:
                full_path = os.path.join(dirpath, fname)
                try:
                    size = os.path.getsize(full_path)
                    os.remove(full_path)
                    deleted_files += 1
                    freed_bytes   += size
                    dirs_to_check.add(dirpath)
                except OSError as e:
                    errors.append(f"{full_path}: {e}")

    # Remove empty directories (bottom-up)
    for d in sorted(dirs_to_check, key=lambda p: -p.count(os.sep)):
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass

    if deleted_files > 0 or errors:
        print(
            f"retention: deleted {deleted_files} files, "
            f"freed {freed_bytes / 1024 / 1024:.2f} MB"
            + (f", {len(errors)} errors" if errors else ""),
            file=sys.stderr
        )

    return {
        'deleted_files': deleted_files,
        'freed_bytes':   freed_bytes,
        'errors':        errors,
    }


async def run_retention_task(interval_seconds: int = 3600):
    """
    Async wrapper for use as a FastAPI lifespan background task.
    Runs delete_old_mseed_files() every interval_seconds.
    """
    import asyncio
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            from database import get_settings
            s = get_settings()
            root           = s.get('archive_root',  '/opt/data/archive')
            retention_days = int(s.get('retention_days', 7))
        except Exception:
            root, retention_days = '/opt/data/archive', 7

        await asyncio.to_thread(delete_old_mseed_files, root, retention_days)
