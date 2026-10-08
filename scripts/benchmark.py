from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import tempfile
import time
from pathlib import Path

from ops_copilot.runtime import IncidentRuntime
from ops_copilot.store import IncidentStore


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * fraction))]


async def run(sessions: int) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory() as directory:
        runtime = IncidentRuntime(IncidentStore(str(Path(directory) / "bench.db")))
        latencies = []
        started = time.perf_counter()
        for index in range(sessions):
            session = runtime.store.create(f"synthetic incident {index}")
            item_started = time.perf_counter()
            await runtime.start_analysis(session.session_id, "Analyze packet loss and alarm timeline")
            result = await runtime.wait(session.session_id)
            latencies.append((time.perf_counter() - item_started) * 1000)
            if result.status.value != "completed":
                raise RuntimeError(f"session ended as {result.status.value}")
        elapsed = time.perf_counter() - started
        return {
            "sessions": sessions,
            "success_rate": 1.0,
            "throughput_sessions_per_second": round(sessions / elapsed, 2),
            "latency_mean_ms": round(statistics.mean(latencies), 3),
            "latency_p50_ms": round(percentile(latencies, 0.50), 3),
            "latency_p95_ms": round(percentile(latencies, 0.95), 3),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.sessions)), indent=2))


if __name__ == "__main__":
    main()

