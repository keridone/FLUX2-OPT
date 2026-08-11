import argparse
import csv
import json
from pathlib import Path


METRICS = {
    "duration": "gpu__time_duration.sum",
    "dram_pct": "gpu__dram_throughput.avg.pct_of_peak_sustained_elapsed",
    "compute_memory_pct": "gpu__compute_memory_throughput.avg.pct_of_peak_sustained_elapsed",
    "sm_pct": "sm__throughput.avg.pct_of_peak_sustained_elapsed",
    "issue_pct": "sm__issue_active.avg.pct_of_peak_sustained_elapsed",
    "tensor_pct": "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_elapsed",
    "active_warps_pct": "sm__warps_active.avg.pct_of_peak_sustained_active",
    "l1tex_pct": "l1tex__throughput.avg.pct_of_peak_sustained_active",
    "registers_per_thread": "launch__registers_per_thread",
    "shared_memory_kib": "launch__shared_mem_per_block",
    "block_size": "launch__block_size",
    "grid_size": "launch__grid_size",
}


def number(value: str) -> float:
    return float(value.replace(",", ""))


def classify(row: dict[str, object]) -> str:
    dram = float(row["dram_pct"])
    sm = float(row["sm_pct"])
    warps = float(row["active_warps_pct"])
    if dram >= 70:
        return "memory_bandwidth"
    if warps < 25 and dram < 40:
        return "occupancy_latency_compute"
    if sm >= 65 and sm >= dram * 1.5:
        return "compute_throughput"
    return "mixed_compute_memory"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    records: list[dict[str, object]] = []
    for path in sorted(args.input_dir.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if len(rows) < 3 or "Kernel Name" not in rows[0]:
            continue
        header, units, values = rows[:3]
        unit_map = dict(zip(header, units))
        value_map = dict(zip(header, values))
        record: dict[str, object] = {
            "source_file": path.name,
            "kernel_name": value_map["Kernel Name"],
        }
        for label, metric in METRICS.items():
            record[label] = number(value_map[metric])
            record[f"{label}_unit"] = unit_map[metric]
        duration_scale = {"ns": 0.001, "us": 1.0, "ms": 1000.0, "s": 1_000_000.0}
        record["duration_us"] = float(record["duration"]) * duration_scale[str(record["duration_unit"])]
        record["classification"] = classify(record)
        records.append(record)

    fieldnames = [key for key in records[0] if not key.endswith("_unit")]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    args.output_json.write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
