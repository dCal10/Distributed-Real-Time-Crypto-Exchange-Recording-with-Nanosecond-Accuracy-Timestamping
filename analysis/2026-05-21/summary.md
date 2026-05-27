# Analysis snapshot — data/binance_nic/2026-05-21/*.parquet

## Coverage
- venue: binance
- rows: 9,257,886
- hours: 17.51
- files: 14,243

## Wire latency (ms)
| n | mean | p50 | p75 | p90 | p95 | p99 | p99.9 | max | stddev |
|---|---|---|---|---|---|---|---|---|---|
| 9,261,886 | 1.481 | 1.382 | 1.757 | 1.962 | 2.342 | 6.627 | 17.692 | 213.992 | 1.644 |

## Pickup lag (µs)
| n | mean | p50 | p95 | p99 | p99.9 | max |
|---|---|---|---|---|---|---|
| 9,268,784 | 563.128 | 210.975 | 1848.893 | 5977.36 | 16327.887 | 206428.609 |

## TCP coalescing
- total: 9,272,487
- unique NIC ts: 4,471,831
- coalesced: 51.77%

## Per-stream latency
| symbol | stream | n | mean | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| ADAUSDT | adausdt@depth@100ms | 292,301 | 0.914 | 0.898 | 1.247 | 1.414 | 141.139 |
| ADAUSDT | adausdt@trade | 66,456 | 1.74 | 1.598 | 2.905 | 9.648 | 50.587 |
| AVAXUSDT | avaxusdt@depth@100ms | 412,365 | 0.887 | 0.891 | 1.241 | 1.401 | 175.992 |
| AVAXUSDT | avaxusdt@trade | 193,840 | 1.673 | 1.589 | 2.343 | 7.735 | 107.983 |
| BTCUSDT | btcusdt@depth@100ms | 630,093 | 0.937 | 0.923 | 1.296 | 1.478 | 211.701 |
| BTCUSDT | btcusdt@trade | 1,894,307 | 1.949 | 1.778 | 3.43 | 8.551 | 148.71 |
| DOGEUSDT | dogeusdt@depth@100ms | 458,020 | 0.91 | 0.9 | 1.249 | 1.398 | 172.992 |
| DOGEUSDT | dogeusdt@trade | 463,526 | 1.713 | 1.61 | 2.547 | 8.75 | 146.338 |
| ETHUSDT | ethusdt@depth@100ms | 628,136 | 0.93 | 0.903 | 1.272 | 1.48 | 211.26 |
| ETHUSDT | ethusdt@trade | 1,959,855 | 1.893 | 1.75 | 3.217 | 8.447 | 154.191 |
| LINKUSDT | linkusdt@depth@100ms | 400,669 | 0.951 | 0.948 | 1.295 | 1.454 | 200.992 |
| LINKUSDT | linkusdt@trade | 124,259 | 1.631 | 1.573 | 2.143 | 7.865 | 213.992 |
| SOLUSDT | solusdt@depth@100ms | 470,808 | 0.956 | 0.955 | 1.309 | 1.467 | 152.338 |
| SOLUSDT | solusdt@trade | 436,326 | 1.772 | 1.644 | 2.729 | 9.477 | 121.34 |
| XRPUSDT | xrpusdt@depth@100ms | 486,168 | 0.92 | 0.894 | 1.24 | 1.404 | 209.26 |
| XRPUSDT | xrpusdt@trade | 349,655 | 1.742 | 1.635 | 2.595 | 8.574 | 177.992 |

## Top outliers
| symbol | stream | observed_at | lat_ms | pickup_us |
|---|---|---|---|---|
| LINKUSDT | linkusdt@trade | 2026-05-21 16:34:46.186032+00:00 | 213.992 | 39040.019 |
| LINKUSDT | linkusdt@trade | 2026-05-21 16:34:46.188089+00:00 | 213.992 | 41097.166 |
| LINKUSDT | linkusdt@trade | 2026-05-21 16:34:46.188138+00:00 | 213.992 | 41146.697 |
| LINKUSDT | linkusdt@trade | 2026-05-21 16:34:46.188172+00:00 | 213.992 | 41181.004 |
| BTCUSDT | btcusdt@depth@100ms | 2026-05-21 16:38:18.826149+00:00 | 211.701 | 447.747 |
| ETHUSDT | ethusdt@depth@100ms | 2026-05-21 16:38:18.826429+00:00 | 211.26 | 168.694 |
| XRPUSDT | xrpusdt@depth@100ms | 2026-05-21 16:38:18.826528+00:00 | 209.26 | 267.997 |
| LINKUSDT | linkusdt@depth@100ms | 2026-05-21 16:34:46.188204+00:00 | 200.992 | 41212.348 |
| LINKUSDT | linkusdt@depth@100ms | 2026-05-21 16:29:20.524728+00:00 | 200.757 | 77971.52 |
| LINKUSDT | linkusdt@depth@100ms | 2026-05-21 17:14:50.047151+00:00 | 200.191 | 959.658 |
| BTCUSDT | btcusdt@depth@100ms | 2026-05-21 16:29:16.036146+00:00 | 193.893 | 28252.857 |
| ETHUSDT | ethusdt@depth@100ms | 2026-05-21 16:29:16.040935+00:00 | 192.893 | 33041.742 |
| XRPUSDT | xrpusdt@depth@100ms | 2026-05-21 16:29:16.040999+00:00 | 190.893 | 33105.61 |
| LINKUSDT | linkusdt@depth@100ms | 2026-05-21 16:38:18.826576+00:00 | 180.26 | 315.551 |
| XRPUSDT | xrpusdt@trade | 2026-05-21 16:34:46.188310+00:00 | 177.992 | 41318.432 |