import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import threading
import time
from pathlib import Path

try:
    import psutil
except ImportError:  # The benchmark remains usable without host RSS sampling.
    psutil = None


REMOTE_ROOT = Path(r"E:\flux")
SD_ROOT = REMOTE_ROOT / "sdcpp"
SD_CLI = SD_ROOT / "runtime" / "sd-cli.exe"
MODEL = SD_ROOT / "models" / "flux-2-klein-4b-Q8_0.gguf"
LLM = SD_ROOT / "models" / "Qwen3-4B-Q4_K_M.gguf"
VAE = SD_ROOT / "models" / "split_files" / "vae" / "flux2-vae.safetensors"
CUDA_RUNTIME = REMOTE_ROOT / ".venv" / "Lib" / "site-packages" / "nvidia" / "cuda_runtime" / "bin"
CUBLAS = REMOTE_ROOT / ".venv" / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin"
BENCHMARK_ROOT = REMOTE_ROOT / "benchmark"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

TIMING_PATTERNS = {
    "reference_encode_seconds": re.compile(r"encode_first_stage completed, taking ([0-9.]+)s"),
    "conditioning_seconds": re.compile(r"get_learned_condition completed, taking ([0-9.]+)s"),
    "sampling_seconds": re.compile(r"sampling completed, taking ([0-9.]+)s"),
    "decode_seconds": re.compile(r"decode_first_stage completed, taking ([0-9.]+)s"),
    "generation_seconds": re.compile(r"generate_image completed in ([0-9.]+)s"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def clean_log(text: str) -> str:
    return ANSI_RE.sub("", text).replace("\r", "")


def parse_timings(log: str) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for key, pattern in TIMING_PATTERNS.items():
        matches = pattern.findall(log)
        result[key] = float(matches[-1]) if matches else None
    return result


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(CUDA_RUNTIME), str(CUBLAS), env.get("PATH", "")])
    return env


class ResourceSampler:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.stop_event = threading.Event()
        self.peak_gpu_mib = 0.0
        self.peak_gpu_utilization = 0.0
        self.peak_process_rss_mib = 0.0
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        tracked = psutil.Process(self.process.pid) if psutil else None
        while not self.stop_event.wait(0.25):
            try:
                query = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if query.returncode == 0:
                    memory, utilization = [float(item.strip()) for item in query.stdout.strip().split(",")]
                    self.peak_gpu_mib = max(self.peak_gpu_mib, memory)
                    self.peak_gpu_utilization = max(self.peak_gpu_utilization, utilization)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            if tracked:
                try:
                    processes = [tracked, *tracked.children(recursive=True)]
                    rss = sum(item.memory_info().rss for item in processes if item.is_running()) / (1024 * 1024)
                    self.peak_process_rss_mib = max(self.peak_process_rss_mib, rss)
                except (psutil.Error, OSError):
                    pass


def run_sd(command: list[str], log_path: Path) -> dict[str, object]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=runtime_env(),
    )
    sampler = ResourceSampler(process)
    sampler.start()
    stdout, _ = process.communicate()
    sampler.stop()
    elapsed = time.perf_counter() - started
    cleaned = clean_log(stdout)
    log_path.write_text(cleaned, encoding="utf-8")
    if process.returncode != 0:
        raise RuntimeError(f"sd-cli failed ({process.returncode}); see {log_path}")
    metrics: dict[str, object] = parse_timings(cleaned)
    metrics.update(
        {
            "wall_seconds": round(elapsed, 4),
            "peak_gpu_mib": sampler.peak_gpu_mib,
            "peak_gpu_utilization_percent": sampler.peak_gpu_utilization,
            "peak_process_rss_mib": sampler.peak_process_rss_mib,
        }
    )
    return metrics


def base_command(width: int, height: int, seed: int, output: Path, prompt: str) -> list[str]:
    return [
        str(SD_CLI),
        "--diffusion-model", str(MODEL),
        "--vae", str(VAE),
        "--llm", str(LLM),
        "--prompt", prompt,
        "--output", str(output),
        "--width", str(width),
        "--height", str(height),
        "--steps", "4",
        "--cfg-scale", "1.0",
        "--sampling-method", "euler",
        "--diffusion-fa",
        "--offload-to-cpu",
        "--seed", str(seed),
        "--verbose",
    ]


def capture_environment(manifest_path: Path) -> dict[str, object]:
    checks = {
        "runtime": SD_CLI,
        "diffusion_model": MODEL,
        "text_encoder": LLM,
        "vae": VAE,
        "manifest": manifest_path,
        "benchmark_script": Path(__file__).resolve(),
    }
    for label, path in checks.items():
        if not path.exists():
            raise FileNotFoundError(f"missing {label}: {path}")
    nvidia = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    version_result = subprocess.run(
        [str(SD_CLI), "--version"], capture_output=True, text=True, env=runtime_env(), check=False
    )
    version = "\n".join(
        part.strip() for part in (version_result.stdout, version_result.stderr) if part.strip()
    )
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "gpu": nvidia,
        "runtime_version": version,
        "hashes": {label: sha256(path) for label, path in checks.items()},
        "settings": {
            "steps": 4,
            "cfg_scale": 1.0,
            "sampler": "euler",
            "rng": "cuda",
            "diffusion_flash_attention": True,
            "cpu_offload": True,
        },
    }


def prepare_sources(tasks: list[dict[str, object]], dataset_root: Path, width: int, height: int) -> None:
    input_root = dataset_root / "inputs"
    log_root = dataset_root / "source_logs"
    input_root.mkdir(parents=True, exist_ok=True)
    for index, task in enumerate(tasks, 1):
        output = input_root / f"{task['id']}.png"
        if output.exists():
            print(f"SOURCE {index}/{len(tasks)} skip {task['id']}", flush=True)
            continue
        print(f"SOURCE {index}/{len(tasks)} generate {task['id']}", flush=True)
        command = base_command(width, height, int(task["seed"]), output, str(task["source_prompt"]))
        run_sd(command, log_root / f"{task['id']}.log")


def write_quality_template(tasks: list[dict[str, object]], run_root: Path, dataset_root: Path) -> None:
    path = run_root / "quality_review.csv"
    if path.exists():
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "task_id", "category", "target", "input_path", "output_path",
                "instruction_success", "content_preservation", "local_consistency",
                "artifact_free", "notes",
            ]
        )
        for task in tasks:
            writer.writerow(
                [
                    task["id"], task["category"], task["target"],
                    dataset_root / "inputs" / f"{task['id']}.png",
                    run_root / "outputs" / str(task["id"]) / "run_1.png",
                    "", "", "", "", "",
                ]
            )


def benchmark_edits(
    tasks: list[dict[str, object]],
    dataset_root: Path,
    run_root: Path,
    width: int,
    height: int,
    repeats: int,
    resume: bool,
) -> list[dict[str, object]]:
    records_path = run_root / "records.json"
    records: list[dict[str, object]] = []
    if records_path.exists():
        if not resume:
            raise FileExistsError(f"run already exists: {records_path}; use --resume or a new --run-id")
        records = json.loads(records_path.read_text(encoding="utf-8"))
    completed = {(item["task_id"], item["repeat"]) for item in records}

    warmup_output = run_root / "warmup.png"
    if not warmup_output.exists():
        first = tasks[0]
        command = base_command(width, height, int(first["seed"]), warmup_output, str(first["edit_instruction"]))
        command.extend(["-r", str(dataset_root / "inputs" / f"{first['id']}.png")])
        print("WARMUP", flush=True)
        run_sd(command, run_root / "logs" / "warmup.log")

    total = len(tasks) * repeats
    current = len(completed)
    for task in tasks:
        input_path = dataset_root / "inputs" / f"{task['id']}.png"
        if not input_path.exists():
            raise FileNotFoundError(f"missing source image: {input_path}")
        for repeat in range(1, repeats + 1):
            key = (task["id"], repeat)
            if key in completed:
                continue
            current += 1
            output = run_root / "outputs" / str(task["id"]) / f"run_{repeat}.png"
            log = run_root / "logs" / str(task["id"]) / f"run_{repeat}.log"
            output.parent.mkdir(parents=True, exist_ok=True)
            command = base_command(width, height, int(task["seed"]), output, str(task["edit_instruction"]))
            command.extend(["-r", str(input_path)])
            print(f"EDIT {current}/{total} {task['id']} repeat={repeat}", flush=True)
            metrics = run_sd(command, log)
            record: dict[str, object] = {
                "task_id": task["id"],
                "category": task["category"],
                "target": task["target"],
                "seed": task["seed"],
                "repeat": repeat,
                "input_path": str(input_path),
                "output_path": str(output),
                "log_path": str(log),
                "input_sha256": sha256(input_path),
                "output_sha256": sha256(output) if output.exists() else None,
                **metrics,
            }
            records.append(record)
            records_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def summarize(records: list[dict[str, object]], run_root: Path) -> dict[str, object]:
    numeric_fields = [
        "wall_seconds", "reference_encode_seconds", "conditioning_seconds",
        "sampling_seconds", "decode_seconds", "generation_seconds",
        "peak_gpu_mib", "peak_gpu_utilization_percent", "peak_process_rss_mib",
    ]
    summary: dict[str, object] = {"sample_count": len(records), "metrics": {}, "categories": {}}
    for field in numeric_fields:
        values = [float(item[field]) for item in records if item.get(field) is not None]
        if values:
            summary["metrics"][field] = {
                "median": round(statistics.median(values), 4),
                "p95": round(percentile(values, 0.95), 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
            }
    for category in sorted({str(item["category"]) for item in records}):
        values = [float(item["wall_seconds"]) for item in records if item["category"] == category]
        summary["categories"][category] = {
            "count": len(values),
            "wall_seconds_median": round(statistics.median(values), 4),
            "wall_seconds_p95": round(percentile(values, 0.95), 4),
        }
    (run_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FLUX.2 season/weather editing baseline benchmark")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-id", default="baseline-bfbef5b-q8-v1")
    parser.add_argument("--mode", choices=["prepare", "baseline", "all"], default="all")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    tasks = manifest["tasks"]
    width, height = manifest["resolution"]
    dataset_root = BENCHMARK_ROOT / "datasets" / manifest["name"]
    run_root = BENCHMARK_ROOT / "runs" / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    environment_path = run_root / "environment.json"
    if not environment_path.exists():
        environment_path.write_text(
            json.dumps(capture_environment(args.manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if args.mode in {"prepare", "all"}:
        prepare_sources(tasks, dataset_root, width, height)
    if args.mode in {"baseline", "all"}:
        records = benchmark_edits(tasks, dataset_root, run_root, width, height, args.repeats, args.resume)
        write_quality_template(tasks, run_root, dataset_root)
        summary = summarize(records, run_root)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
