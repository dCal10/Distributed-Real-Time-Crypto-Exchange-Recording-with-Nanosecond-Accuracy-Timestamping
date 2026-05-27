#!/usr/bin/env bash
# Install the collector systemd unit and the S3 sync cron entry on a fresh
# EC2 box. Idempotent: safe to re-run after a git pull or config change.
#
# Usage: sudo ./infra/scripts/install.sh <region-short> <venue>
#   region-short: tokyo | virginia | ohio | london | hong-kong
#   venue:        binance | binance_nic | coinbase | coinbase_nic
#                 | okx | okx_nic | kalshi | polymarket
#
# Fully venue/region-parametric: no per-venue branches. <venue> must be a
# key in collector.exchanges.EXCHANGES (the entrypoint validates it); the
# `*_nic` variants install identically to their production counterparts.
# The S3 bucket is NOT mapped here: <region-short> is passed verbatim to
# the cron line, and sync-to-s3.sh derives the bucket by the convention
# group19-ptp-<region-short> (its single source of truth). So:
#   sudo ./infra/scripts/install.sh virginia  coinbase_nic  -> group19-ptp-virginia
#   sudo ./infra/scripts/install.sh hong-kong okx_nic       -> group19-ptp-hong-kong
#   sudo ./infra/scripts/install.sh tokyo     binance       -> group19-ptp-tokyo (unchanged)
set -euo pipefail

REGION_SHORT="${1:?usage: install.sh <region-short> <venue>}"
VENUE="${2:?usage: install.sh <region-short> <venue>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNIT_SRC="${REPO_ROOT}/infra/systemd/group19-collector@.service"
UNIT_DST="/etc/systemd/system/group19-collector@.service"
SYNC_SCRIPT="${REPO_ROOT}/infra/scripts/sync-to-s3.sh"
# Referenced by the unit's ExecStartPre via this absolute path; present
# automatically after git clone. Re-asserting +x here guards against the
# exec bit not surviving the clone (same reason SYNC_SCRIPT is chmod'd).
HW_TS_SCRIPT="${REPO_ROOT}/infra/scripts/enable-hw-timestamping.sh"
LOG_FILE="/var/log/sync-to-s3.log"

if [[ $EUID -ne 0 ]]; then
  echo "must run as root (use sudo)" >&2
  exit 1
fi

command -v systemctl >/dev/null || { echo "systemctl not found" >&2; exit 1; }
command -v aws       >/dev/null || { echo "aws cli not found; install awscli" >&2; exit 1; }
command -v crontab   >/dev/null || { echo "crontab not found; install cronie" >&2; exit 1; }
[[ -f "$UNIT_SRC"  ]] || { echo "missing $UNIT_SRC"  >&2; exit 1; }
[[ -f "$SYNC_SCRIPT" ]] || { echo "missing $SYNC_SCRIPT" >&2; exit 1; }
[[ -f "$HW_TS_SCRIPT" ]] || { echo "missing $HW_TS_SCRIPT (required by the unit's ExecStartPre)" >&2; exit 1; }
chmod +x "$SYNC_SCRIPT"
chmod +x "$HW_TS_SCRIPT"

cp "$UNIT_SRC" "$UNIT_DST"
systemctl daemon-reload
systemctl enable "group19-collector@${VENUE}.service" >/dev/null
echo "systemd: unit installed and enabled for venue=${VENUE}"

CRON_LINE="*/5 * * * * ${SYNC_SCRIPT} ${REGION_SHORT} >> ${LOG_FILE} 2>&1"
CURRENT_CRON="$(crontab -u ec2-user -l 2>/dev/null || true)"
if grep -Fq "$SYNC_SCRIPT" <<< "$CURRENT_CRON"; then
  echo "cron:    entry already present; not duplicating"
else
  ( echo "$CURRENT_CRON"; echo "$CRON_LINE" ) | crontab -u ec2-user -
  echo "cron:    added entry: $CRON_LINE"
fi

touch "$LOG_FILE"
chown ec2-user:ec2-user "$LOG_FILE"

cat <<EOF

install complete.

next steps (run manually, in order):
  sudo systemctl start group19-collector@${VENUE}
  journalctl -fu group19-collector@${VENUE}        # tail logs, ctrl-C to detach
  # after 5-10 min, verify per infra/README.md "Post-deploy verification"
EOF
