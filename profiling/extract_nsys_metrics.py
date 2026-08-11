import argparse
import csv
import json
import sqlite3
import statistics
from pathlib import Path


def percentile(values: list[int], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return float(ordered[index])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--downsample", type=int, default=100)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    metric_names = list(
        connection.execute(
            "SELECT typeId, metricId, metricName FROM TARGET_INFO_GPU_METRICS ORDER BY metricId"
        )
    )
    kernel_window = connection.execute(
        "SELECT MIN(start) AS start, MAX(end) AS end, SUM(end-start) AS busy FROM CUPTI_ACTIVITY_KIND_KERNEL"
    ).fetchone()
    gpu = dict(connection.execute("SELECT * FROM TARGET_INFO_GPU LIMIT 1").fetchone())

    summary_rows: list[dict[str, object]] = []
    series_path = args.output_dir / "gpu_metrics_downsampled.csv"
    with series_path.open("w", newline="", encoding="utf-8") as series_file:
        series_writer = csv.writer(series_file)
        series_writer.writerow(["timestamp_ns", "relative_ms", "metric_id", "metric_name", "value"])
        for metric in metric_names:
            rows = list(
                connection.execute(
                    "SELECT timestamp, value FROM GPU_METRICS WHERE typeId=? AND metricId=? ORDER BY timestamp",
                    (metric["typeId"], metric["metricId"]),
                )
            )
            values = [int(row["value"]) for row in rows]
            active_values = [
                int(row["value"])
                for row in rows
                if kernel_window["start"] <= row["timestamp"] <= kernel_window["end"]
            ]
            nonzero = [value for value in active_values if value != 0]
            summary_rows.append(
                {
                    "metric_id": metric["metricId"],
                    "metric_name": metric["metricName"],
                    "samples": len(values),
                    "active_samples": len(active_values),
                    "active_min": min(active_values) if active_values else None,
                    "active_median": statistics.median(active_values) if active_values else None,
                    "active_mean": statistics.fmean(active_values) if active_values else None,
                    "active_p95": percentile(active_values, 0.95) if active_values else None,
                    "active_max": max(active_values) if active_values else None,
                    "active_nonzero_mean": statistics.fmean(nonzero) if nonzero else None,
                }
            )
            for row in rows[:: args.downsample]:
                series_writer.writerow(
                    [
                        row["timestamp"],
                        (row["timestamp"] - kernel_window["start"]) / 1_000_000,
                        metric["metricId"],
                        metric["metricName"],
                        row["value"],
                    ]
                )

    summary_path = args.output_dir / "gpu_metrics_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)

    info = {
        "gpu": gpu,
        "kernel_window": {
            "start_ns": kernel_window["start"],
            "end_ns": kernel_window["end"],
            "span_ms": (kernel_window["end"] - kernel_window["start"]) / 1_000_000,
            "summed_kernel_time_ms": kernel_window["busy"] / 1_000_000,
        },
        "metric_count": len(metric_names),
        "downsample_factor": args.downsample,
        "source_database": str(args.database),
    }
    (args.output_dir / "gpu_profile_info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
