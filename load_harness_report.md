# Drishti Load Harness Report

Generated at: `2026-05-14T06:10:55.578156+00:00`

## Scenario

- Merchants: `100`
- Orders per merchant: `500`
- Estimated source records: `117,500`
- Estimated normalized rows: `102,500`
- Chat turns: `200` at concurrency `25`
- Agent scans: `100` at concurrency `25`

## Synthetic Results

| Workload | Count | Mean ms | P50 ms | P95 ms | Max ms |
|---|---:|---:|---:|---:|---:|
| chat citation turn | 200 | 6.74 | 6.74 | 12.41 | 13.01 |
| agent deterministic scan | 100 | 0.24 | 0.24 | 0.40 | 0.45 |

## Interpretation

- This harness stresses the citation validator and deterministic agent scan shape without relying on third-party APIs.
- At 10k merchants, `source_records` grows first and should be hash-partitioned by `merchant_id` before it reaches hundreds of millions of rows.
- Chat tool queries must stay bounded by `merchant_id`, indexed time windows, and explicit `LIMIT`s; rollups are the next step for repeated monthly aggregates.
- Agent runs should remain queued and staggered; the current worker already hashes scheduled runs across a four-hour window.

## Database Smoke

- Count query duration: `9763.73 ms`

| Table | Rows |
|---|---:|
| `merchants` | `3` |
| `source_records` | `65` |
| `orders` | `49` |
| `shipments` | `12` |
| `payments` | `2` |
| `agent_runs` | `12` |
| `agent_findings` | `17` |
| `chat_messages` | `10` |
| `tool_calls` | `10` |
