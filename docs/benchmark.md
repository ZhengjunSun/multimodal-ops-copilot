# Reproducible benchmark

Measured on 2026-10-08 with Python 3.12 on a local Windows workstation, SQLite, the deterministic offline provider, no uploaded media, and 100 sequential synthetic incident sessions.

| Metric | Result |
|---|---:|
| Successful sessions | 100 / 100 |
| Throughput | 48.57 sessions/s |
| Mean analysis latency | 16.094 ms |
| P50 analysis latency | 15.752 ms |
| P95 analysis latency | 19.835 ms |

Reproduce with `python scripts/benchmark.py --sessions 100`.

This isolates session orchestration, storage, event publication, and offline synthesis. It does not claim production vision, speech, upload, or remote-model throughput. Those adapters must be measured separately with representative files and deployment hardware.

