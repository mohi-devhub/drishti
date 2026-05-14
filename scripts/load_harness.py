from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from drishti.chat.citation_validator import validate_citations
from drishti.chat.tools.registry import CitedAggregate, CitedRow, ToolResult
from drishti.config import get_settings
from drishti.db.session import create_engine


@dataclass(frozen=True)
class HarnessConfig:
    merchants: int
    orders_per_merchant: int
    chat_turns: int
    agent_runs: int
    concurrency: int
    output: Path
    database_smoke: bool


async def main() -> None:
    args = parse_args()
    config = HarnessConfig(
        merchants=args.merchants,
        orders_per_merchant=args.orders_per_merchant,
        chat_turns=args.chat_turns,
        agent_runs=args.agent_runs,
        concurrency=args.concurrency,
        output=Path(args.output),
        database_smoke=args.database_smoke,
    )
    started = datetime.now(UTC)
    synthetic = await run_synthetic(config)
    database = await run_database_smoke() if config.database_smoke else None
    report = render_report(config, started=started, synthetic=synthetic, database=database)
    config.output.write_text(report, encoding="utf-8")
    print(f"Wrote {config.output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drishti scale/load harness")
    parser.add_argument("--merchants", type=int, default=100)
    parser.add_argument("--orders-per-merchant", type=int, default=500)
    parser.add_argument("--chat-turns", type=int, default=200)
    parser.add_argument("--agent-runs", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--output", default="load_harness_report.md")
    parser.add_argument(
        "--database-smoke",
        action="store_true",
        help="Also run lightweight count queries against DATABASE_URL.",
    )
    return parser.parse_args()


async def run_synthetic(config: HarnessConfig) -> dict:
    semaphore = asyncio.Semaphore(config.concurrency)
    chat_latencies = await gather_latencies(
        count=config.chat_turns,
        semaphore=semaphore,
        worker=lambda index: synthetic_chat_turn(index, config.orders_per_merchant),
    )
    agent_latencies = await gather_latencies(
        count=config.agent_runs,
        semaphore=semaphore,
        worker=lambda index: synthetic_agent_scan(index, config.orders_per_merchant),
    )
    source_records = config.merchants * int(config.orders_per_merchant * 2.35)
    normalized_rows = config.merchants * int(config.orders_per_merchant * 2.05)
    return {
        "source_records": source_records,
        "normalized_rows": normalized_rows,
        "chat": summarize(chat_latencies),
        "agent": summarize(agent_latencies),
    }


async def gather_latencies(count: int, semaphore: asyncio.Semaphore, worker) -> list[float]:
    async def run_one(index: int) -> float:
        async with semaphore:
            started = time.perf_counter()
            await worker(index)
            return (time.perf_counter() - started) * 1000

    return await asyncio.gather(*(run_one(index) for index in range(count)))


async def synthetic_chat_turn(index: int, orders_per_merchant: int) -> None:
    await asyncio.sleep(0)
    row_count = min(100, orders_per_merchant)
    rows = [
        CitedRow(
            row_id=f"order:{uuid4()}",
            values={"total_paise": 100000 + index, "line_items_count": 1},
            source="shopify",
            source_record_id=f"order-{index}-{row_index}",
            raw_record_id=str(uuid4()),
            fetched_from="synthetic://orders",
            synced_at=datetime.now(UTC).isoformat(),
        )
        for row_index in range(row_count)
    ]
    total = sum(int(row.values["total_paise"]) for row in rows)
    result = ToolResult(
        result_id=f"tr_{uuid4().hex[:12]}",
        tool_name="query_orders",
        args={"limit": row_count},
        rows=rows,
        aggregates=[
            CitedAggregate(
                agg_id="agg_orders_count",
                label="orders_count",
                value=len(rows),
                unit="count",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="COUNT(orders)",
            ),
            CitedAggregate(
                agg_id="agg_orders_total_paise",
                label="orders_total_paise",
                value=total,
                unit="inr_paise",
                derived_from_row_ids=[row.row_id for row in rows],
                formula="SUM(orders.total_paise)",
            ),
        ],
    )
    answer = (
        "Revenue is "
        f"<cite agg_orders_total_paise>₹{total / 100:,.0f}</cite> across "
        f"<cite agg_orders_count>{len(rows)}</cite> orders."
    )
    validation = validate_citations(answer, [result], auto_attach=False)
    if not validation.passed:
        raise RuntimeError(f"synthetic citation validation failed: {validation.failures}")


async def synthetic_agent_scan(index: int, orders_per_merchant: int) -> None:
    await asyncio.sleep(0)
    sample_size = min(orders_per_merchant, 500)
    freight_loss = 0
    rto_count = 0
    for order_index in range(sample_size):
        if (order_index + index) % 7 == 0:
            freight_loss += 25000
            rto_count += 1
    if rto_count and freight_loss <= 0:
        raise RuntimeError("synthetic agent invariant failed")


async def run_database_smoke() -> dict:
    engine = create_engine(get_settings())
    tables = [
        "merchants",
        "source_records",
        "orders",
        "shipments",
        "payments",
        "agent_runs",
        "agent_findings",
        "chat_messages",
        "tool_calls",
    ]
    counts = {}
    started = time.perf_counter()
    try:
        async with engine.connect() as conn:
            for table in tables:
                result = await conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table}")
                counts[table] = int(result.scalar_one())
    finally:
        await engine.dispose()
    return {"duration_ms": (time.perf_counter() - started) * 1000, "counts": counts}


def summarize(values: list[float]) -> dict:
    sorted_values = sorted(values)
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "p50_ms": percentile(sorted_values, 0.50),
        "p95_ms": percentile(sorted_values, 0.95),
        "max_ms": max(values),
    }


def percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * quantile)))
    return sorted_values[index]


def render_report(
    config: HarnessConfig,
    *,
    started: datetime,
    synthetic: dict,
    database: dict | None,
) -> str:
    chat = synthetic["chat"]
    agent = synthetic["agent"]
    lines = [
        "# Drishti Load Harness Report",
        "",
        f"Generated at: `{started.isoformat()}`",
        "",
        "## Scenario",
        "",
        f"- Merchants: `{config.merchants}`",
        f"- Orders per merchant: `{config.orders_per_merchant}`",
        f"- Estimated source records: `{synthetic['source_records']:,}`",
        f"- Estimated normalized rows: `{synthetic['normalized_rows']:,}`",
        f"- Chat turns: `{config.chat_turns}` at concurrency `{config.concurrency}`",
        f"- Agent scans: `{config.agent_runs}` at concurrency `{config.concurrency}`",
        "",
        "## Synthetic Results",
        "",
        "| Workload | Count | Mean ms | P50 ms | P95 ms | Max ms |",
        "|---|---:|---:|---:|---:|---:|",
        row("chat citation turn", chat),
        row("agent deterministic scan", agent),
        "",
        "## Interpretation",
        "",
        "- This harness stresses the citation validator and deterministic agent scan shape without relying on third-party APIs.",
        "- At 10k merchants, `source_records` grows first and should be hash-partitioned by `merchant_id` before it reaches hundreds of millions of rows.",
        "- Chat tool queries must stay bounded by `merchant_id`, indexed time windows, and explicit `LIMIT`s; rollups are the next step for repeated monthly aggregates.",
        "- Agent runs should remain queued and staggered; the current worker already hashes scheduled runs across a four-hour window.",
    ]
    if database:
        lines.extend(
            [
                "",
                "## Database Smoke",
                "",
                f"- Count query duration: `{database['duration_ms']:.2f} ms`",
                "",
                "| Table | Rows |",
                "|---|---:|",
                *[f"| `{table}` | `{count:,}` |" for table, count in database["counts"].items()],
            ]
        )
    return "\n".join(lines) + "\n"


def row(label: str, summary: dict) -> str:
    return (
        f"| {label} | {summary['count']} | {summary['mean_ms']:.2f} | "
        f"{summary['p50_ms']:.2f} | {summary['p95_ms']:.2f} | {summary['max_ms']:.2f} |"
    )


if __name__ == "__main__":
    asyncio.run(main())
