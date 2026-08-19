import hashlib
import importlib.util
import json
import random
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(r"E:\flux")
MATRIX_PATH = ROOT / "optimization" / "parameter-matrix.json"
MANIFEST_PATH = ROOT / "benchmark" / "code" / "tasks.json"
BASELINE_MODULE_PATH = ROOT / "benchmark" / "code" / "run_baseline.py"
RUN_ROOT = ROOT / "optimization" / "runs" / "parameter-screen-v2"


def load_baseline_module():
    spec = importlib.util.spec_from_file_location("flux2_baseline", BASELINE_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {BASELINE_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CPU_OFFLOAD = False
    return module


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def median(values):
    return round(statistics.median(values), 4)


def main() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    fixed = matrix["fixed_protocol"]
    task = next(item for item in manifest["tasks"] if item["id"] == fixed["task"])
    width, height = fixed["resolution"]
    input_path = ROOT / "benchmark" / "datasets" / manifest["name"] / "inputs" / f"{task['id']}.png"
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    baseline = load_baseline_module()
    experiments = matrix["experiments"]
    control = experiments[0]
    middle = experiments[1:]
    random.Random(20260819).shuffle(middle)
    ordered = [control, *middle, {**control, "id": f"{control['id']}-final"}]
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    (RUN_ROOT / "execution-order.json").write_text(
        json.dumps([item["id"] for item in ordered], indent=2), encoding="utf-8"
    )

    records = []
    for experiment in ordered:
        experiment_root = RUN_ROOT / experiment["id"]
        experiment_root.mkdir(parents=True, exist_ok=True)
        warmups = max(2, int(fixed["warmups"]))
        for repeat in range(1 - warmups, int(fixed["repeats"]) + 1):
            label = f"warmup-{repeat + warmups}" if repeat <= 0 else f"run-{repeat}"
            output = experiment_root / f"{label}.png"
            log = experiment_root / f"{label}.log"
            command = baseline.base_command(
                width, height, int(task["seed"]), output, str(task["edit_instruction"])
            )
            command = [arg for arg in command if arg != "--diffusion-fa"]
            command.extend(["-r", str(input_path), *experiment["args"]])
            print(f"{experiment['id']} {label}", flush=True)
            metrics = baseline.run_sd(command, log)
            if repeat > 0:
                records.append(
                    {
                        "experiment_id": experiment["id"],
                        "repeat": repeat,
                        "args": experiment["args"],
                        "output_sha256": digest(output),
                        **metrics,
                    }
                )
                (RUN_ROOT / "records.json").write_text(
                    json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
                )

    summaries = []
    for experiment in ordered:
        rows = [row for row in records if row["experiment_id"] == experiment["id"]]
        summaries.append(
            {
                "experiment_id": experiment["id"],
                "args": experiment["args"],
                "samples": len(rows),
                "wall_seconds_median": median([row["wall_seconds"] for row in rows]),
                "generation_seconds_median": median([row["generation_seconds"] for row in rows]),
                "reference_encode_seconds_median": median([row["reference_encode_seconds"] for row in rows]),
                "conditioning_seconds_median": median([row["conditioning_seconds"] for row in rows]),
                "sampling_seconds_median": median([row["sampling_seconds"] for row in rows]),
                "decode_seconds_median": median([row["decode_seconds"] for row in rows]),
                "peak_gpu_mib_max": max(row["peak_gpu_mib"] for row in rows),
                "output_hashes": sorted({row["output_sha256"] for row in rows}),
            }
        )
    control_drift = round(
        100
        * (summaries[-1]["wall_seconds_median"] - summaries[0]["wall_seconds_median"])
        / summaries[0]["wall_seconds_median"],
        3,
    )
    result = {
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "input_sha256": digest(input_path),
        "control_drift_percent": control_drift,
        "stable": abs(control_drift) <= 3.0,
        "experiments": summaries,
    }
    (RUN_ROOT / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
