#!/usr/bin/env bash
# Enable hardware RX timestamping on the NIC. Must run before any *_nic
# collector. Required because AWS Nitro + ENA driver supports HW RX
# timestamping but defaults to disabled; the SIOCSHWTSTAMP ioctl flips RX
# configuration to 1.
#
# Interface selection (parameterized 2026-05-18, supersedes the hardcoded
# ens5 so the script is region-portable):
#
#   enable-hw-timestamping.sh [iface]
#
#   - Explicit [iface] arg wins (e.g. `enable-hw-timestamping.sh eth0`).
#   - No arg (how the systemd ExecStartPre invokes it): auto-detect the
#     active ENA interface as the first non-loopback link in the UP state.
#     The collector unit has After=network-online.target, so the NIC is
#     already UP when this runs. This is what lets a fresh region
#     self-configure regardless of ens5 / eth0 / ens6 naming.
#   - If auto-detect yields nothing (e.g. `ip` absent): fall back to ens5,
#     preserving the original Tokyo behavior for backward compatibility.
#
# Idempotent — safe to run on every service start (re-setting the same RX
# filter is a no-op). Requires CAP_NET_ADMIN, provided by the systemd
# ExecStartPre `+` prefix which runs this as root.
# See ADR-0012 deployment addendum for full discovery story.

IFACE="${1:-}"
if [[ -z "$IFACE" ]]; then
  IFACE="$(ip -br link show up 2>/dev/null | awk '$1 != "lo" {print $1; exit}')"
fi
IFACE="${IFACE:-ens5}"

exec /home/ec2-user/aws-ptp-crypto-recording/.venv/bin/python - "$IFACE" <<'PY'
import sys, socket, struct, fcntl, ctypes
SIOCSHWTSTAMP = 0x89b0
HWTSTAMP_FILTER_ALL = 1
iface = sys.argv[1].encode()
hwconfig = struct.pack('iii', 0, 0, HWTSTAMP_FILTER_ALL)
buf = ctypes.create_string_buffer(hwconfig, len(hwconfig))
ifreq = struct.pack('16sP', iface, ctypes.addressof(buf))
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
fcntl.ioctl(s.fileno(), SIOCSHWTSTAMP, ifreq)
s.close()
PY
