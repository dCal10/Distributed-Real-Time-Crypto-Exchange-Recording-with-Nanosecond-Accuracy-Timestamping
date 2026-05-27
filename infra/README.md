# infra/ — EC2 deploy assets

Systemd unit, S3 sync cron, and install script for landing the PTP-synced
collector on a per-region EC2 instance. One instance per venue; the same files
serve every region by parameterizing on `<region-short>` and `<venue>`.

## Bucket naming

Per-region S3 buckets follow the convention `group19-ptp-<region-short>`:

| Region          | AWS code         | region-short  | Bucket               |
|-----------------|------------------|---------------|----------------------|
| Tokyo           | `ap-northeast-1` | `tokyo`       | `group19-ptp-tokyo`  |
| N. Virginia     | `us-east-1`      | `virginia`    | `group19-ptp-virginia` |
| Ohio            | `us-east-2`      | `ohio`        | `group19-ptp-ohio`   |
| London          | `eu-west-2`      | `london`      | `group19-ptp-london` |
| Hong Kong       | `ap-east-1`      | `hong-kong`   | `group19-ptp-hong-kong` |

## Prerequisites on a fresh EC2 box

1. Amazon Linux 2023 on a PTP-supported instance family (M7g preferred per
   ADR; M7i acceptable).
2. ENA driver >= 2.10.0 with `phc_enable=1` (reboot after enabling).
3. `chrony` configured with `refclock PHC /dev/ptp_ena poll 0 delay 0.000010 prefer`.
4. `chronyc tracking` shows `Reference ID : 50484330 (PHC0)` with
   `RMS offset` under 1 microsecond (it will be much tighter once warm).
5. `aws` CLI installed (`sudo dnf install -y awscli`) and an instance role with
   `s3:PutObject` / `s3:ListBucket` on the venue's bucket.
6. `cronie` installed and `crond` enabled (`sudo systemctl enable --now crond`).
7. **For the `binance_nic` NIC-hardware-timestamp path only:** RX hardware
   timestamping must be enabled at the device level (see next section). The
   `phc_enable=1` PTP clock (item 2) and the `SO_TIMESTAMPING` socket option
   are necessary but NOT sufficient on AWS Nitro.

## NIC hardware timestamping (binance_nic path)

AWS Nitro / ENA supports RX hardware timestamping but ships it **disabled by
default**. Setting `SO_TIMESTAMPING` with `SOF_TIMESTAMPING_RX_HARDWARE` on
the socket is not enough: the ENA driver only attaches hardware timestamps
once RX timestamping is enabled at the device level via the `SIOCSHWTSTAMP`
ioctl with `HWTSTAMP_FILTER_ALL`. That flips RX configuration from `0` to
`1` in `/sys/class/net/<iface>/device/hw_packet_timestamping_state`
(interface `ens5` on the Tokyo box). Without it, `recvmsg` ancillary data
returns a zero hardware timestamp and the collector silently degrades to
the software fallback.

[`infra/scripts/enable-hw-timestamping.sh`](scripts/enable-hw-timestamping.sh)
applies the ioctl. It is idempotent (safe to re-run; safe on both the
`binance` and `binance_nic` services) and runs automatically as a systemd
`ExecStartPre` with the `+` prefix (executes as root regardless of the
service user). No manual step is required on deploy; this section documents
*why* the ExecStartPre exists. Empirical finding 2026-05-16: AWS docs do not
state this for the Python `recvmsg` path. See ADR-0012 "Deployment addendum".

## One-time bucket creation per region

Run once from any machine with AWS creds for the target region. Replace
`tokyo` and `ap-northeast-1` for other regions.

```bash
aws s3api create-bucket \
  --bucket group19-ptp-tokyo \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1

aws s3api put-bucket-versioning \
  --bucket group19-ptp-tokyo \
  --versioning-configuration Status=Enabled
```

## Deploy procedure

On the target EC2 box, as `ec2-user`:

```bash
# 1. Clone and set up venv
cd /home/ec2-user
git clone <gitlab-repo-url> aws-ptp-crypto-recording
cd aws-ptp-crypto-recording
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Verify PTP plumbing BEFORE starting the collector
chronyc tracking | grep -E "Reference ID|RMS offset"
ls -l /dev/ptp_ena                      # symlink exists
ethtool -T enX0 | grep -E "PTP|software" # NIC supports timestamping

# 3. Install systemd unit + S3 sync cron (Tokyo + binance example)
sudo ./infra/scripts/install.sh tokyo binance

# 4. Start the collector
sudo systemctl start group19-collector@binance
journalctl -fu group19-collector@binance     # ctrl-C detaches; service keeps running
```

The systemd unit is a *template* (`group19-collector@.service`). The instance
name after `@` becomes the `--venue` argument. So `group19-collector@coinbase`
on the Virginia box, `group19-collector@kalshi` on the Ohio box, and so on.

## Deploying additional regions (Coinbase → us-east-1, OKX → ap-east-1)

`coinbase_nic` and `okx_nic` are built and deploy-ready (2026-05-16). They
follow the exact `binance_nic` pattern: subclass the production collector,
override `run()` only, inherit `parse()`. Nothing in the systemd template or
`install.sh` is venue-specific, so bringing them up is the same procedure as
Tokyo with two argument changes. Do these once per regional EC2 box, as
`ec2-user`.

| Venue          | AWS region     | region-short | Bucket                   | systemd instance              |
|----------------|----------------|--------------|--------------------------|-------------------------------|
| Coinbase (NIC) | `us-east-1`    | `virginia`   | `group19-ptp-virginia`   | `group19-collector@coinbase_nic` |
| OKX (NIC)      | `ap-east-1`    | `hong-kong`  | `group19-ptp-hong-kong`  | `group19-collector@okx_nic`      |

**0. Before the box exists.** Create the per-region bucket once (see
"One-time bucket creation per region" above, substituting the region code
and `region-short` from the table). `us-east-1` is the S3 global default,
so omit `--create-bucket-configuration LocationConstraint=...` for Virginia;
keep it for `ap-east-1`.

**1. Clone, venv, deps** (identical to the Tokyo deploy procedure):

```bash
cd /home/ec2-user
git clone <gitlab-repo-url> aws-ptp-crypto-recording
cd aws-ptp-crypto-recording
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # wsproto is required for *_nic
```

The `*_nic` venues need `wsproto` (in `requirements.txt`). The production
parents do not; the import is lazy so a missing wsproto only fails when a
`_nic` venue is actually selected.

**2. chrony / PTP** (identical to Tokyo, item 2-4 of "Prerequisites"):
`refclock PHC /dev/ptp_ena poll 0 delay 0.000010 prefer`, then confirm
`chronyc tracking` shows `Reference ID : 50484330 (PHC0)` with sub-
microsecond RMS offset. PTP discipline is region-independent: every AWS
region references the same atomic-clock fleet, so cross-region timestamps
remain comparable. Do not start the collector until `PHC0` is locked.

**3. AWS credentials for S3 sync.** Tokyo uses an instance role. For the
additional regions, configure the per-region **collector IAM user** access
keys as a named CLI profile for `ec2-user` (the user `cron` runs
`sync-to-s3.sh` as):

```bash
sudo -u ec2-user aws configure --profile group19-collector
# AWS Access Key ID:     <collector IAM user key for this region>
# AWS Secret Access Key: <collector IAM user secret>
# Default region name:   us-east-1   (or ap-east-1 for OKX)
# Default output format: json
```

The collector IAM user needs only `s3:PutObject` + `s3:ListBucket` on that
region's bucket (same policy as the Tokyo instance role). If you instead
attach an instance role with that policy, skip the profile step and leave
`sync-to-s3.sh` as-is. If you use the profile, export
`AWS_PROFILE=group19-collector` in the cron environment (prepend
`AWS_PROFILE=group19-collector ` to the `sync-to-s3.sh` cron line, or set
it in `ec2-user`'s crontab) so the every-5-min sync authenticates. Verify:
`sudo -u ec2-user aws s3 ls s3://group19-ptp-virginia/ --profile group19-collector`
returns without an access error (empty listing is fine pre-first-sync).

**4. SIOCSHWTSTAMP — required for NIC hardware stamps.** Every `*_nic`
venue needs RX hardware timestamping toggled on at the device level via the
`SIOCSHWTSTAMP` ioctl (see "NIC hardware timestamping" above); the socket
option alone is insufficient on AWS Nitro/ENA, and without the ioctl the
collector silently degrades to software timestamps (zero hardware stamp).

> **Resolved 2026-05-18:** the `ExecStartPre` line and
> `infra/scripts/enable-hw-timestamping.sh` are committed and match the
> unit running on Tokyo, so `install.sh` + git clone wire the ioctl
> automatically with no manual step on a fresh region. The script
> auto-detects the active ENA interface (no argument = detect; optional
> interface arg overrides; `ens5` only as last-resort fallback), so it is
> region-portable across `ens5` / `eth0` / `ens6` naming with no per-box
> interface check. **Verify after first start:** confirm RX timestamping
> configuration is on,
> `cat /sys/class/net/<iface>/device/hw_packet_timestamping_state` is `1`
> (`<iface>` from `ip -br link show up`), and that step 7's NIC-coverage
> query reports 100%. If coverage is below 100%, the auto-detected
> interface was wrong; pin it explicitly by passing the interface as the
> script's argument.

**5. Install unit + sync cron** (one command; venue/region parametric):

```bash
# Coinbase on the us-east-1 box:
sudo ./infra/scripts/install.sh virginia coinbase_nic

# OKX on the ap-east-1 box:
sudo ./infra/scripts/install.sh hong-kong okx_nic
```

`install.sh` symlinks the systemd template, enables
`group19-collector@<venue>`, and adds the `*/5 * * * *` cron entry calling
`sync-to-s3.sh <region-short>`. `sync-to-s3.sh` derives the bucket as
`group19-ptp-<region-short>` (its single source of truth — no separate
region→bucket map). The Tokyo `tokyo binance` invocation is unaffected.

**6. Start and tail:**

```bash
sudo systemctl start group19-collector@coinbase_nic    # or @okx_nic
journalctl -fu group19-collector@coinbase_nic          # ctrl-C detaches
```

**7. Validation queries** (run after 5-10 min of recording; the record
`venue` field stays `coinbase`/`okx` even though the sink dir is
`coinbase_nic`/`okx_nic`):

```bash
cd /home/ec2-user/aws-ptp-crypto-recording
.venv/bin/python -c "
import pyarrow.dataset as ds, statistics as st, glob, collections
# coinbase_nic; for OKX use data/okx_nic/*/*.parquet
files = sorted(glob.glob('data/coinbase_nic/*/*.parquet'))[-20:]
t = ds.dataset(files).to_table()
nic = t.column('t_nic_first').to_pylist()
cov = sum(1 for v in nic if v) / len(nic)
jit = [u - n for u, n in zip(t.column('t_ptp_ns').to_pylist(), nic) if n]
print(f'records:               {len(nic)}')
print(f'NIC hw coverage:       {cov*100:.1f}%   (gate: 100%; <100% => SIOCSHWTSTAMP not applied)')
print(f'userspace jitter p50:  {st.median(jit)/1e3:.0f} us' if jit else 'no hw stamps')
print('streams:', dict(collections.Counter(t.column(\"stream\").to_pylist())))
"
# Then confirm S3 is receiving:
tail -n 5 /var/log/sync-to-s3.log
```

Gate: NIC hw coverage **100%**. Anything less means the SIOCSHWTSTAMP
toggle did not take (see step 4) and the data is software-fallback only.
For Coinbase expect `streams` keys `market_trades` + `ticker`; for OKX
`books` + `trades`.

## Post-deploy verification

Run while the collector is recording. Let it run 5-10 min first.

**Step 1: chrony health**

```bash
chronyc tracking
# Reference ID : 50484330 (PHC0)
# Stratum     : 1
# RMS offset  : < 1.0e-06 seconds   <-- gate: sub-microsecond
```

If `Reference ID` is anything other than `PHC0`, chrony is NOT actually
locking onto the NIC clock and `clock_gettime` is reading something else.
Stop and fix this before trusting any captured data.

**Step 2: delta_ns distribution**

```bash
cd /home/ec2-user/aws-ptp-crypto-recording
.venv/bin/python -c "
import pyarrow.dataset as ds, statistics as st, glob
files = sorted(glob.glob('data/binance/*/*.parquet'))[-20:]
t = ds.dataset(files).to_table()
d = t.column('delta_ns').to_pylist()
print(f'records:    {len(d)}')
print(f'median:     {st.median(d)/1e6:.2f} ms')
print(f'p95:        {sorted(d)[int(len(d)*0.95)]/1e6:.2f} ms')
print(f'p99:        {sorted(d)[int(len(d)*0.99)]/1e6:.2f} ms')
print(f'max:        {max(d)/1e6:.2f} ms')
print()
print('streams:')
import collections
for k, v in collections.Counter(t.column('stream').to_pylist()).items():
    print(f'  {k}: {v}')
"
```

**Gate criteria for Tokyo:**

| Metric          | Pass                | Fail action                          |
|-----------------|---------------------|--------------------------------------|
| median delta_ns | < 50 ms             | Check `chronyc tracking`; PTP broken |
| p99 delta_ns    | < 200 ms            | Check NTP fallback; widen capture    |
| `streams` keys  | both depth + trade  | WS combined-stream URL broke         |

If Tokyo lands tight (single-digit ms median typical), the existing
`clock_gettime` path is doing what it should. If it doesn't, debug PTP /
chrony / ENA before scaling to other regions.

## Q7 research spike (run during verify dead time)

The 5-10 min verify capture is mostly waiting. Use that window to run the
SO_TIMESTAMPING viability probe:

```bash
.venv/bin/python tests/spike_so_timestamping.py
```

The output decides whether P2's path (a) is viable. Save the output for
the P2 planning conversation; if path (a) is blocked, the SO_TIMESTAMPING
collector scope grows ~3x.

## Operational notes

- The collector restarts on failure (`Restart=on-failure`,
  `StartLimitBurst=5` over 300 s). A `ConnectionClosed` from Binance after
  24 hours triggers an exit + automatic restart.
- Cron runs `sync-to-s3.sh` every 5 minutes. Sync logs go to
  `/var/log/sync-to-s3.log`. Tail to confirm sync is happening:
  `tail -f /var/log/sync-to-s3.log`.
- Stopping the collector: `sudo systemctl stop group19-collector@<venue>`.
  The Python process gets SIGTERM, asyncio raises CancelledError, and the
  sink's `close()` runs in the entrypoint's `finally`, flushing the last
  buffered records.
- Disabling auto-start at boot: `sudo systemctl disable group19-collector@<venue>`.

## Files in this directory

- `systemd/group19-collector@.service` — templated systemd unit
- `scripts/sync-to-s3.sh` — wraps `aws s3 sync` with `--size-only`
- `scripts/install.sh` — idempotent install of unit + cron
- `README.md` — this file
