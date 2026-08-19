import hashlib
import importlib.util
import json
import statistics
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(r"E:\flux")
HELPER_PATH = ROOT / "optimization" / "benchmark_persistent_server.py"
TASKS_PATH = ROOT / "benchmark" / "code" / "tasks.json"
BASELINE = ROOT / "benchmark" / "runs" / "no-offload-baseline-v1" / "outputs"
OUT = ROOT / "optimization" / "runs" / "persistent-suite-v1"
REPEATS = 3


def load_helper():
    spec = importlib.util.spec_from_file_location("persistent_helper", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gpu_memory_mib():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True, timeout=5,
    )
    return float(result.stdout.strip())


def pixel_metrics(candidate, control_path):
    candidate_array = np.asarray(Image.open(candidate).convert("RGB"), dtype=np.int16)
    control_array = np.asarray(Image.open(control_path).convert("RGB"), dtype=np.int16)
    delta = np.abs(candidate_array - control_array)
    return {
        "mean_absolute_error": round(float(delta.mean()), 6),
        "max_absolute_error": int(delta.max()),
        "candidate_rgb_sha256": hashlib.sha256(candidate_array.astype(np.uint8).tobytes()).hexdigest(),
        "control_rgb_sha256": hashlib.sha256(control_array.astype(np.uint8).tobytes()).hexdigest(),
    }


def percentile(values, fraction):
    return float(np.percentile(np.asarray(values), fraction * 100))


def main():
    helper = load_helper()
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    OUT.mkdir(parents=True, exist_ok=True)

    # Warm up lazy model preparation before measuring steady-state service latency.
    warmup_id = helper.submit(tasks[0])
    warmup = helper.wait_job(warmup_id)
    if warmup["status"] != "completed":
        raise RuntimeError(json.dumps(warmup, indent=2))

    records = []
    initial_memory = gpu_memory_mib()
    for repeat in range(1, REPEATS + 1):
        for index, task in enumerate(tasks, 1):
            started = time.perf_counter()
            job_id = helper.submit(task)
            submitted = time.perf_counter()
            job = helper.wait_job(job_id)
            finished = time.perf_counter()
            if job["status"] != "completed":
                raise RuntimeError(json.dumps(job, indent=2))
            image_bytes = helper.decode_result(job)
            output = OUT / "outputs" / task["id"] / f"run-{repeat}.png"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(image_bytes)
            metrics = pixel_metrics(output, BASELINE / task["id"] / "run_1.png")
            row = {
                "task_id": task["id"], "repeat": repeat,
                "wall_seconds": round(finished - started, 4),
                "submission_seconds": round(submitted - started, 4),
                "gpu_memory_mib_after": gpu_memory_mib(),
                "output_sha256": hashlib.sha256(image_bytes).hexdigest(),
                **metrics,
            }
            records.append(row)
            (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
            print(f"{repeat}/{REPEATS} {index}/{len(tasks)} {task['id']} {row['wall_seconds']:.4f}s mem={row['gpu_memory_mib_after']:.0f}", flush=True)

    latencies = [row["wall_seconds"] for row in records]
    memory = [row["gpu_memory_mib_after"] for row in records]
    deterministic = all(
        len({row["candidate_rgb_sha256"] for row in records if row["task_id"] == task["id"]}) == 1
        for task in tasks
    )
    summary = {
        "run_id": "persistent-suite-v1", "tasks": len(tasks), "repeats": REPEATS,
        "completed_runs": len(records), "failed_runs": 0,
        "latency_seconds": {
            "median": round(statistics.median(latencies), 4),
            "p95": round(percentile(latencies, 0.95), 4),
            "min": round(min(latencies), 4), "max": round(max(latencies), 4),
        },
        "throughput_tasks_per_second": round(1 / statistics.mean(latencies), 4),
        "deterministic_across_repeats": deterministic,
        "baseline_pixel_difference": {
            "mean_absolute_error_median": round(statistics.median(row["mean_absolute_error"] for row in records), 6),
            "mean_absolute_error_max": max(row["mean_absolute_error"] for row in records),
            "max_absolute_error_max": max(row["max_absolute_error"] for row in records),
        },
        "gpu_memory_mib": {
            "after_warmup": initial_memory, "min": min(memory), "max": max(memory),
            "end_minus_start": round(memory[-1] - initial_memory, 2),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
