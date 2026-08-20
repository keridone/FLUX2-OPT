import base64
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path


ROOT = Path(r"E:\flux")
HELPER_PATH = ROOT / "optimization" / "benchmark_persistent_server.py"
TASKS_PATH = ROOT / "benchmark" / "code" / "tasks.json"
OUT = ROOT / "optimization" / "runs" / "timestep-microbatch-v1"
REPEATS = 3


def load_helper():
    spec = importlib.util.spec_from_file_location("persistent_helper", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode_images(job):
    images = (job.get("result") or {}).get("images") or []
    result = []
    for image in images:
        encoded = image.get("b64_json") if isinstance(image, dict) else image
        if encoded.startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        result.append(base64.b64decode(encoded))
    return result


def main():
    helper = load_helper()
    task = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"][0]
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    for repeat in range(1, REPEATS + 1):
        body = helper.payload(task)
        body["batch_count"] = 2
        started = time.perf_counter()
        job_id = helper.request_json("POST", "/sdcpp/v1/img_gen", body)["id"]
        job = helper.wait_job(job_id)
        elapsed = time.perf_counter() - started
        if job["status"] != "completed":
            raise RuntimeError(json.dumps(job, indent=2))
        images = decode_images(job)
        if len(images) != 2:
            raise RuntimeError(f"expected 2 images, got {len(images)}")
        hashes = [hashlib.sha256(image).hexdigest() for image in images]
        records.append({"repeat": repeat, "wall_seconds": round(elapsed, 4),
                        "output_sha256": hashes})
        print(records[-1], flush=True)
    summary = {
        "run_id": "timestep-microbatch-v1",
        "batch_size": 2,
        "repeats": REPEATS,
        "pair_wall_seconds_median": round(statistics.median(x["wall_seconds"] for x in records), 4),
        "throughput_tasks_per_second": round(2 / statistics.mean(x["wall_seconds"] for x in records), 4),
        "deterministic": all(records[0]["output_sha256"] == row["output_sha256"] for row in records[1:]),
        "output_hashes": records[0]["output_sha256"],
    }
    (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
