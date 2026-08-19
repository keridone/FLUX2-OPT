import hashlib
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(r"E:\flux")
BASELINE_MODULE = ROOT / "benchmark" / "code" / "run_baseline.py"
TASKS = ROOT / "benchmark" / "code" / "tasks.json"
INPUT = ROOT / "benchmark" / "datasets" / "season-weather-edit-v1" / "inputs" / "season_001_winter_city.png"
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else "q8-mmq-x64-v1"
CANDIDATE_LABEL = sys.argv[2] if len(sys.argv) > 2 else "candidate-x64"
OUT = ROOT / "optimization" / "runs" / RUN_ID
BINARIES = {
    "control-x128-y128": ROOT / "sdcpp" / "experiments" / "q8-control" / "sd-cli.exe",
    CANDIDATE_LABEL: ROOT / "sdcpp" / "source" / "build-q8-control-vs" / "bin" / "Release" / "sd-cli.exe",
}


def load_module():
    spec = importlib.util.spec_from_file_location("baseline", BASELINE_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CPU_OFFLOAD = False
    return module


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    baseline = load_module()
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
    task = next(x for x in tasks if x["id"] == "season_001_winter_city")
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    # Alternate binaries after independent warmups to reduce ordering bias.
    for label, binary in BINARIES.items():
        (OUT / label).mkdir(parents=True, exist_ok=True)
        baseline.SD_CLI = binary
        for warmup in range(1, 3):
            output = OUT / label / f"warmup-{warmup}.png"
            cmd = baseline.base_command(512, 512, 101, output, task["edit_instruction"])
            cmd.extend(["-r", str(INPUT)])
            baseline.run_sd(cmd, OUT / label / f"warmup-{warmup}.log")
    for repeat in range(1, 6):
        for label, binary in BINARIES.items():
            baseline.SD_CLI = binary
            output = OUT / label / f"run-{repeat}.png"
            cmd = baseline.base_command(512, 512, 101, output, task["edit_instruction"])
            cmd.extend(["-r", str(INPUT)])
            metrics = baseline.run_sd(cmd, OUT / label / f"run-{repeat}.log")
            records.append({
                "variant": label, "repeat": repeat, "binary_sha256": sha256(binary),
                "output_sha256": sha256(output), **metrics,
            })
            (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
            print(f"{label} run-{repeat}: {metrics['wall_seconds']:.4f}s", flush=True)
    summary = {"completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "variants": {}}
    for label in BINARIES:
        rows = [x for x in records if x["variant"] == label]
        summary["variants"][label] = {
            "wall_seconds_median": round(statistics.median(x["wall_seconds"] for x in rows), 4),
            "generation_seconds_median": round(statistics.median(x["generation_seconds"] for x in rows), 4),
            "sampling_seconds_median": round(statistics.median(x["sampling_seconds"] for x in rows), 4),
            "peak_gpu_mib_max": max(x["peak_gpu_mib"] for x in rows),
            "binary_sha256": rows[0]["binary_sha256"],
            "output_hashes": sorted({x["output_sha256"] for x in rows}),
        }
    control = summary["variants"]["control-x128-y128"]["wall_seconds_median"]
    candidate = summary["variants"][CANDIDATE_LABEL]["wall_seconds_median"]
    summary["candidate_speedup_percent"] = round(100 * (control - candidate) / control, 3)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
