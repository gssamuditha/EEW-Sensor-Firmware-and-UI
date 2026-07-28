#!/bin/bash
# cleanup_archive.sh — miniSEED retention cron script
#
# A fallback bash script for the EEW Sensor pipeline that deletes SDS
# miniSEED files older than the specified retention window.
#
# Usage:
#   /opt/eew/scripts/cleanup_archive.sh [RETENTION_DAYS] [ARCHIVE_ROOT]
#
# Example (via cron, every day at 02:00):
#   0 2 * * * /opt/eew/scripts/cleanup_archive.sh 7 /home/crisislab/data/archive

RETENTION_DAYS="${1:-7}"
ARCHIVE_ROOT="${2:-/home/crisislab/data/archive}"

if [ ! -d "$ARCHIVE_ROOT" ]; then
    echo "Archive root directory not found: $ARCHIVE_ROOT"
    exit 0
fi

# 1. Delete .D miniSEED files older than $RETENTION_DAYS
find "$ARCHIVE_ROOT" -type f -name "*.D" -mtime +$RETENTION_DAYS -delete

# 2. Cleanup any directories that are now empty
find "$ARCHIVE_ROOT" -type d -empty -delete
