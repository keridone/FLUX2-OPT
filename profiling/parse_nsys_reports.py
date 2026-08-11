import argparse
import csv
import json
from pathlib import Path


def rows_after_header(path: Path, first_column: str) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith(first_column + ","))
    return list(csv.DictReader(lines[index:]))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    args = parser.parse_args()

    kernel_raw = rows_after_header(args.input_dir / "cuda_gpu_kern_sum.csv", "Time (%)")
    kernels = [
        {
            "rank": rank,
            "time_percent": float(row["Time (%)"]),
            "total_time_ms": int(row["Total Time (ns)"]) / 1_000_000,
            "instances": int(row["Instances"]),
            "average_us": float(row["Avg (ns)"]) / 1_000,
            "median_us": float(row["Med (ns)"]) / 1_000,
            "min_us": int(row["Min (ns)"]) / 1_000,
            "max_us": int(row["Max (ns)"]) / 1_000,
            "kernel_name": row["Name"],
        }
        for rank, row in enumerate(kernel_raw, 1)
    ]
    write_csv(args.input_dir / "kernel_summary_clean.csv", kernels)

    memory_time_raw = rows_after_header(args.input_dir / "cuda_gpu_mem_time_sum.csv", "Time (%)")
    memory_ops = [
        {
            "time_percent": float(row["Time (%)"]),
            "total_time_ms": int(row["Total Time (ns)"]) / 1_000_000,
            "count": int(row["Count"]),
            "average_us": float(row["Avg (ns)"]) / 1_000,
            "operation": row["Operation"],
        }
        for row in memory_time_raw
    ]
    write_csv(args.input_dir / "memory_time_summary_clean.csv", memory_ops)

    memory_size_raw = rows_after_header(args.input_dir / "cuda_gpu_mem_size_sum.csv", "Total (MB)")
    memory_sizes = [
        {
            "total_mb": float(row["Total (MB)"]),
            "count": int(row["Count"]),
            "average_mb": float(row["Avg (MB)"]),
            "max_mb": float(row["Max (MB)"]),
            "operation": row["Operation"],
        }
        for row in memory_size_raw
    ]
    write_csv(args.input_dir / "memory_size_summary_clean.csv", memory_sizes)

    api_raw = rows_after_header(args.input_dir / "cuda_api_sum.csv", "Time (%)")
    apis = [
        {
            "rank": rank,
            "time_percent": float(row["Time (%)"]),
            "total_time_ms": int(row["Total Time (ns)"]) / 1_000_000,
            "calls": int(row["Num Calls"]),
            "average_us": float(row["Avg (ns)"]) / 1_000,
            "api_name": row["Name"],
        }
        for rank, row in enumerate(api_raw, 1)
    ]
    write_csv(args.input_dir / "cuda_api_summary_clean.csv", apis)

    profile_info = json.loads(
        (args.input_dir / "metrics" / "gpu_profile_info.json").read_text(encoding="utf-8")
    )
    span_ms = profile_info["kernel_window"]["span_ms"]
    kernel_ms = sum(row["total_time_ms"] for row in kernels)
    memory_ms = sum(row["total_time_ms"] for row in memory_ops)
    summary = {
        "kernel_count": sum(row["instances"] for row in kernels),
        "unique_kernel_count": len(kernels),
        "kernel_window_ms": span_ms,
        "summed_kernel_time_ms": kernel_ms,
        "summed_memory_operation_time_ms": memory_ms,
        "kernel_duty_percent": kernel_ms / span_ms * 100,
        "gpu_operation_duty_percent": (kernel_ms + memory_ms) / span_ms * 100,
        "estimated_non_gpu_operation_gap_ms": span_ms - kernel_ms - memory_ms,
        "h2d_total_mb": next(row["total_mb"] for row in memory_sizes if "Host-to-Device" in row["operation"]),
        "h2d_total_time_ms": next(row["total_time_ms"] for row in memory_ops if "Host-to-Device" in row["operation"]),
        "top_10_kernel_time_percent": sum(row["time_percent"] for row in kernels[:10]),
    }
    (args.input_dir / "nsys_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
