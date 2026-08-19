import hashlib
import importlib.util
import json
import os
import re
import statistics
import subprocess
import threading
import time
from pathlib import Path


ROOT = Path(r"E:\flux")
BASELINE_MODULE = ROOT / "benchmark" / "code" / "run_baseline.py"
TASKS_PATH = ROOT / "benchmark" / "code" / "tasks.json"
DATASET = ROOT / "benchmark" / "datasets" / "season-weather-edit-v1" / "inputs"
OUT = ROOT / "optimization" / "runs" / "parallel-v1"
REPEATS = 3


def load_baseline():
    spec = importlib.util.spec_from_file_location("baseline", BASELINE_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CPU_OFFLOAD = False
    return module


def file_hash(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gpu_state():
    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, errors="replace", timeout=5,
    )
    used = float(query.stdout.strip()) if query.returncode == 0 else 0.0
    processes = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, errors="replace", timeout=5,
    )
    pids = [int(line.strip()) for line in processes.stdout.splitlines() if line.strip().isdigit()]
    return used, pids


class GroupMonitor:
    def __init__(self):
        self.stop = threading.Event()
        self.peak_gpu_mib = 0.0
        self.peak_gpu_processes = 0
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.wait(0.05):
            try:
                memory, pids = gpu_state()
                self.peak_gpu_mib = max(self.peak_gpu_mib, memory)
                self.peak_gpu_processes = max(self.peak_gpu_processes, len(pids))
            except (OSError, subprocess.SubprocessError):
                pass


def command_for(baseline, task, output):
    command = baseline.base_command(512, 512, int(task["seed"]), output, task["edit_instruction"])
    command.extend(["-r", str(DATASET / f"{task['id']}.png")])
    return command


def run_processes(commands, log_paths):
    env = os.environ.copy()
    env.update(load_baseline().runtime_env())
    monitor = GroupMonitor()
    started = time.perf_counter()
    processes = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace", env=env)
                 for cmd in commands]
    monitor.thread.start()
    outputs = [process.communicate(timeout=300)[0] for process in processes]
    monitor.stop.set()
    monitor.thread.join()
    elapsed = time.perf_counter() - started
    records = []
    for process, output, log_path in zip(processes, outputs, log_paths):
        cleaned = output.replace("\r", "")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(cleaned, encoding="utf-8")
        records.append({"returncode": process.returncode,
                        "cuda_oom": bool(re.search(r"out of memory|alloc failed", cleaned, re.I)),
                        "illegal_access": "illegal memory access" in cleaned.lower()})
    return elapsed, monitor, records


def main():
    baseline = load_baseline()
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    selected = [next(item for item in tasks if item["id"] == task_id) for task_id in
                ["season_001_winter_city", "weather_001_heavy_rain_city"]]
    OUT.mkdir(parents=True, exist_ok=True)
    records = []

    for repeat in range(1, REPEATS + 1):
        # Control: two distinct tasks, separate model loads, serial execution.
        case = OUT / "sequential" / f"repeat-{repeat}"
        case.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        peak = 0.0
        outputs = []
        for index, task in enumerate(selected):
            output = case / f"task-{index + 1}.png"
            metrics = baseline.run_sd(command_for(baseline, task, output), case / f"task-{index + 1}.log")
            peak = max(peak, metrics["peak_gpu_mib"])
            outputs.append(file_hash(output))
        records.append({"mode": "sequential_two_processes", "repeat": repeat,
                        "wall_seconds": round(time.perf_counter() - started, 4),
                        "tasks_completed": 2, "peak_gpu_mib": peak, "output_hashes": outputs})

        # One process/model load producing two samples of the same edit request.
        case = OUT / "batch-count-2" / f"repeat-{repeat}"
        case.mkdir(parents=True, exist_ok=True)
        output = case / "batch.png"
        command = command_for(baseline, selected[0], output) + ["--batch-count", "2"]
        elapsed, monitor, status = run_processes([command], [case / "batch.log"])
        images = sorted(case.glob("*.png"))
        records.append({"mode": "single_process_batch_count_2", "repeat": repeat,
                        "wall_seconds": round(elapsed, 4), "tasks_completed": len(images),
                        "peak_gpu_mib": monitor.peak_gpu_mib, "peak_gpu_processes": monitor.peak_gpu_processes,
                        "processes": status, "output_hashes": [file_hash(path) for path in images]})

        # Two different requests begin together in two independent model processes.
        case = OUT / "concurrent" / f"repeat-{repeat}"
        case.mkdir(parents=True, exist_ok=True)
        outputs = [case / "task-1.png", case / "task-2.png"]
        commands = [command_for(baseline, task, output) for task, output in zip(selected, outputs)]
        elapsed, monitor, status = run_processes(commands, [case / "task-1.log", case / "task-2.log"])
        completed = [path for path in outputs if path.exists()]
        records.append({"mode": "concurrent_two_processes", "repeat": repeat,
                        "wall_seconds": round(elapsed, 4), "tasks_completed": len(completed),
                        "peak_gpu_mib": monitor.peak_gpu_mib, "peak_gpu_processes": monitor.peak_gpu_processes,
                        "processes": status, "output_hashes": [file_hash(path) for path in completed]})
        (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(json.dumps(records[-3:], indent=2), flush=True)

    summary = {"run_id": "parallel-v1", "cpu_offload": False, "repeats": REPEATS, "modes": {}}
    for mode in sorted({row["mode"] for row in records}):
        rows = [row for row in records if row["mode"] == mode]
        successful = [row for row in rows if row["tasks_completed"] == 2 and
                      all(item.get("returncode") == 0 for item in row.get("processes", [{"returncode": 0}]))]
        summary["modes"][mode] = {
            "successful_repeats": len(successful),
            "wall_seconds_median": round(statistics.median(row["wall_seconds"] for row in successful), 4) if successful else None,
            "throughput_tasks_per_second": round(2 / statistics.median(row["wall_seconds"] for row in successful), 4) if successful else 0,
            "peak_gpu_mib_max": max(row["peak_gpu_mib"] for row in rows),
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
