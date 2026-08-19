import base64
import hashlib
import json
import statistics
import time
import urllib.request
from pathlib import Path


ROOT = Path(r"E:\flux")
BASE_URL = "http://127.0.0.1:12345"
TASKS = ROOT / "benchmark" / "code" / "tasks.json"
INPUTS = ROOT / "benchmark" / "datasets" / "season-weather-edit-v1" / "inputs"
OUT = ROOT / "optimization" / "runs" / "persistent-server-v1"
TASK_IDS = ["season_001_winter_city", "weather_001_heavy_rain_city"]


def request_json(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(BASE_URL + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def image_data(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def payload(task):
    return {
        "prompt": task["edit_instruction"], "negative_prompt": "",
        "width": 512, "height": 512, "strength": 0.75,
        "seed": int(task["seed"]), "batch_count": 1,
        "auto_resize_ref_image": True, "ref_images": [image_data(INPUTS / f"{task['id']}.png")],
        "sample_params": {
            "sample_method": "euler", "sample_steps": 4
        },
        "output_format": "png", "output_compression": 100,
    }


def submit(task):
    return request_json("POST", "/sdcpp/v1/img_gen", payload(task))["id"]


def wait_job(job_id):
    while True:
        job = request_json("GET", f"/sdcpp/v1/jobs/{job_id}")
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)


def decode_result(job):
    result = job.get("result") or {}
    images = result.get("images") or result.get("data") or []
    first = images[0] if images else None
    if isinstance(first, dict):
        first = first.get("b64_json") or first.get("data") or first.get("image")
    if not isinstance(first, str):
        raise RuntimeError(f"unrecognized job result: {result.keys()}")
    if "," in first and first.startswith("data:"):
        first = first.split(",", 1)[1]
    return base64.b64decode(first)


def run_pair(tasks, repeat, warmup=False):
    started = time.perf_counter()
    ids = [submit(task) for task in tasks]
    submitted = time.perf_counter()
    jobs = [wait_job(job_id) for job_id in ids]
    elapsed = time.perf_counter() - started
    if any(job["status"] != "completed" for job in jobs):
        raise RuntimeError(json.dumps(jobs, indent=2))
    hashes = []
    for index, job in enumerate(jobs):
        data = decode_result(job)
        hashes.append(hashlib.sha256(data).hexdigest())
        if not warmup:
            path = OUT / "outputs" / f"repeat-{repeat}-task-{index + 1}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return {"repeat": repeat, "wall_seconds": round(elapsed, 4),
            "submission_seconds": round(submitted - started, 4),
            "output_hashes": hashes,
            "jobs": [{"id": job["id"], "created": job["created"], "started": job["started"],
                      "completed": job["completed"]} for job in jobs]}


def main():
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
    selected = [next(task for task in tasks if task["id"] == task_id) for task_id in TASK_IDS]
    OUT.mkdir(parents=True, exist_ok=True)
    run_pair(selected[:1], 0, warmup=True)
    records = []
    for repeat in range(1, 4):
        row = run_pair(selected, repeat)
        records.append(row)
        (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(json.dumps(row, indent=2), flush=True)
    median = statistics.median(row["wall_seconds"] for row in records)
    control = 12.2753
    summary = {
        "run_id": "persistent-server-v1", "tasks_per_pair": 2, "repeats": 3,
        "persistent_pair_wall_seconds_median": round(median, 4),
        "throughput_tasks_per_second": round(2 / median, 4),
        "separate_cli_pair_wall_seconds_control": control,
        "wall_time_reduction_percent": round(100 * (control - median) / control, 3),
        "output_hashes_by_task": [sorted({row["output_hashes"][i] for row in records}) for i in range(2)],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
