import importlib.util
import json
import statistics
import time
from pathlib import Path


ROOT = Path(r"E:\flux")
HELPER_PATH = ROOT / "optimization" / "benchmark_persistent_server.py"
TASKS_PATH = ROOT / "benchmark" / "code" / "tasks.json"
OUT = ROOT / "optimization" / "runs" / "condition-cache-baseline-v1"
REPEATS = 10


def load_helper():
    spec = importlib.util.spec_from_file_location("persistent_helper", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(helper, task, group, index):
    started = time.perf_counter()
    job = helper.wait_job(helper.submit(task))
    elapsed = time.perf_counter() - started
    if job["status"] != "completed":
        raise RuntimeError(json.dumps(job, indent=2))
    return {
        "group": group,
        "index": index,
        "task_id": task["id"],
        "wall_seconds": round(elapsed, 4),
    }


def describe(rows):
    values = [row["wall_seconds"] for row in rows]
    return {
        "runs": len(values),
        "median_seconds": round(statistics.median(values), 4),
        "mean_seconds": round(statistics.mean(values), 4),
        "min_seconds": round(min(values), 4),
        "max_seconds": round(max(values), 4),
    }


def main():
    helper = load_helper()
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    OUT.mkdir(parents=True, exist_ok=True)

    # Remove one-time lazy initialization from the comparison.
    warmup = helper.wait_job(helper.submit(tasks[0]))
    if warmup["status"] != "completed":
        raise RuntimeError(json.dumps(warmup, indent=2))

    records = []
    for index in range(REPEATS):
        records.append(run(helper, tasks[0], "identical", index + 1))
    for index in range(REPEATS):
        records.append(run(helper, tasks[index % len(tasks)], "distinct", index + 1))
    (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    identical = [row for row in records if row["group"] == "identical"]
    distinct = [row for row in records if row["group"] == "distinct"]
    summary = {
        "run_id": "condition-cache-baseline-v1",
        "purpose": "Detect cross-request prompt/reference-image cache behavior",
        "identical_requests": describe(identical),
        "distinct_requests": describe(distinct),
        "interpretation": (
            "No cross-request cache hit is exposed by the API; server phase logs must "
            "confirm encode_first_stage and get_learned_condition execute per request."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
