import importlib.util
import json
import statistics
import time
from pathlib import Path


ROOT = Path(r"E:\flux")
HELPERS = ROOT / "optimization" / "run_parallel_experiment.py"
TASKS_PATH = ROOT / "benchmark" / "code" / "tasks.json"
DATASET = ROOT / "benchmark" / "datasets" / "season-weather-edit-v1" / "inputs"
OUT = ROOT / "optimization" / "runs" / "parallel-scaling-v1"
REPEATS = 3


def load_helpers():
    spec = importlib.util.spec_from_file_location("parallel_helpers", HELPERS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    helpers = load_helpers()
    baseline = helpers.load_baseline()
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    ids = ["season_001_winter_city", "weather_001_heavy_rain_city", "season_002_autumn_lake"]
    selected = [next(task for task in tasks if task["id"] == task_id) for task_id in ids]
    records = []

    for repeat in range(1, REPEATS + 1):
        for count in [1, 2, 4]:
            case = OUT / f"batch-{count}" / f"repeat-{repeat}"
            case.mkdir(parents=True, exist_ok=True)
            output = case / "batch.png"
            command = helpers.command_for(baseline, selected[0], output) + ["--batch-count", str(count)]
            elapsed, monitor, status = helpers.run_processes([command], [case / "batch.log"])
            images = sorted(case.glob("*.png"))
            records.append({"family": "single_process_batch", "parallelism": count, "repeat": repeat,
                            "wall_seconds": round(elapsed, 4), "tasks_completed": len(images),
                            "peak_gpu_mib": monitor.peak_gpu_mib, "processes": status})

        for count in [1, 2, 3]:
            case = OUT / f"concurrent-{count}" / f"repeat-{repeat}"
            case.mkdir(parents=True, exist_ok=True)
            outputs = [case / f"task-{index + 1}.png" for index in range(count)]
            commands = [helpers.command_for(baseline, task, output)
                        for task, output in zip(selected[:count], outputs)]
            elapsed, monitor, status = helpers.run_processes(
                commands, [case / f"task-{index + 1}.log" for index in range(count)])
            records.append({"family": "independent_processes", "parallelism": count, "repeat": repeat,
                            "wall_seconds": round(elapsed, 4),
                            "tasks_completed": sum(path.exists() for path in outputs),
                            "peak_gpu_mib": monitor.peak_gpu_mib, "processes": status})
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"repeat {repeat}/{REPEATS} complete", flush=True)

    summary = {"run_id": "parallel-scaling-v1", "cpu_offload": False, "repeats": REPEATS, "cells": []}
    for family in ["single_process_batch", "independent_processes"]:
        for count in [1, 2, 4] if family == "single_process_batch" else [1, 2, 3]:
            rows = [row for row in records if row["family"] == family and row["parallelism"] == count]
            valid = [row for row in rows if row["tasks_completed"] == count and
                     all(process["returncode"] == 0 for process in row["processes"])]
            wall = statistics.median(row["wall_seconds"] for row in valid) if valid else None
            summary["cells"].append({
                "family": family, "parallelism": count, "successful_repeats": len(valid),
                "wall_seconds_median": round(wall, 4) if wall else None,
                "throughput_tasks_per_second": round(count / wall, 4) if wall else 0,
                "mean_seconds_per_task": round(wall / count, 4) if wall else None,
                "peak_gpu_mib_max": max(row["peak_gpu_mib"] for row in rows),
            })
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
