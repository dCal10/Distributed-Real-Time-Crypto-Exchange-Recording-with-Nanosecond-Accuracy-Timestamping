#!/usr/bin/env bash
# Sync ./data/ to s3://group19-ptp-<region>/ every cron interval.
# Run from cron; --size-only because Parquet files are immutable once flushed,
# so size match implies content match (no mtime drift re-uploads).
#
# Usage: sync-to-s3.sh <region-short-name>
#   region-short-name: tokyo | virginia | ohio | london | hong-kong
set -euo pipefail

REGION_SHORT="${1:?usage: sync-to-s3.sh <region-short-name>}"
BUCKET="group19-ptp-${REGION_SHORT}"
DATA_DIR="${DATA_DIR:-/home/ec2-user/aws-ptp-crypto-recording/data}"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "[$(date -u +%FT%TZ)] sync-to-s3: $DATA_DIR not present yet; skipping"
  exit 0
fi

echo "[$(date -u +%FT%TZ)] sync-to-s3: $DATA_DIR -> s3://$BUCKET/"
aws s3 sync "$DATA_DIR/" "s3://$BUCKET/" --size-only --no-progress
echo "[$(date -u +%FT%TZ)] sync-to-s3: done"
