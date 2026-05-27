# 45-Second Pitch Outline, IE421 Group 19

## Goal

Pitch the project to a mixed audience (recruiters, executives, technical experts) in 45 seconds. Land both the "what" and the "why it's hard."

## Beats (target ~120 words spoken total)

**[0:00-0:08] HOOK, the problem**
Suggested phrasing: "Modern trading depends on knowing exactly when market data arrived, to the nanosecond. Vendors charge for this. Production trading firms build their own."

**[0:08-0:20] WHAT WE BUILT, the project in two sentences**
Suggested phrasing: "We built that pipeline for cryptocurrency exchanges and prediction markets. It runs on AWS, co-located with the exchange's matching engine, and stamps every market update at the network card with hardware timestamps disciplined to nanosecond precision."

**[0:20-0:32] HEADLINE RESULT, the measured number**
Suggested phrasing: "Over 17 hours we recorded 9.3 million market events from Binance in Tokyo. Median wire-arrival latency: 1.4 milliseconds. We also discovered that AWS's hardware timestamping silently degrades without a specific device-level enable, not documented anywhere we could find."

**[0:32-0:42] WHY IT MATTERS / HANDOFF**
Suggested phrasing: "The architecture generalizes to five exchanges in four regions. Multi-region deployment is the natural next step. Repository, full report, and contact below."

**[0:42-0:45] OUTRO, name and thank you**
Suggested phrasing: "I'm Yichen. Thanks for watching."

## Visual suggestions (overlaid while speaking)

- 0:00-0:08: text "Trading depends on nanoseconds"
- 0:08-0:20: architecture diagram fading in
- 0:20-0:32: latency histogram (chart 01) plus the 1.4 ms number on screen
- 0:32-0:42: world map showing 4 candidate regions, Tokyo highlighted
- 0:42-0:45: QR code to final_report.md, names, contact

## Variants

- Speed up to 110%: about 5 seconds of buffer recovered if running long
- Drop the AWS-discovery sentence (0:25-0:30) if running very long
- Add a sentence about the dual-NIC-timestamp schema if running short
