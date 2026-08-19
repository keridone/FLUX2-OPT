import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path


ROOT = Path(r"E:\flux")
HELPER_PATH = ROOT / "optimization" / "benchmark_persistent_server.py"
TASKS_PATH = ROOT / "benchmark" / "code" / "tasks.json"
OUT = ROOT / "optimization" / "runs" / "text-condition-cache-v1"
CASES = 5


def load_helper():
    spec = importlib.util.spec_from_file_location("persistent_helper", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def submit(helper, prompt_task, ref_task):
    body = helper.payload(prompt_task)
    body["ref_images"] = [helper.image_data(helper.INPUTS / f"{ref_task['id']}.png")]
    return helper.request_json("POST", "/sdcpp/v1/img_gen", body)["id"]


def run_case(helper, group, case_index, round_index, prompt_task, ref_task):
    started = time.perf_counter()
    job = helper.wait_job(submit(helper, prompt_task, ref_task))
    elapsed = time.perf_counter() - started
    if job["status"] != "completed":
        raise RuntimeError(json.dumps(job, indent=2))
    output = helper.decode_result(job)
    return {
        "group": group,
        "case": case_index,
        "round": round_index,
        "prompt_task_id": prompt_task["id"],
        "reference_task_id": ref_task["id"],
        "wall_seconds": round(elapsed, 4),
        "output_sha256": hashlib.sha256(output).hexdigest(),
    }


def describe(records, group, round_index):
    values = [row["wall_seconds"] for row in records
              if row["group"] == group and row["round"] == round_index]
    return {
        "runs": len(values),
        "median_seconds": round(statistics.median(values), 4),
        "mean_seconds": round(statistics.mean(values), 4),
        "min_seconds": round(min(values), 4),
        "max_seconds": round(max(values), 4),
    }


def main():
    helper = load_helper()
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"][:CASES]
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    groups = {
        "same_prompt_same_reference": [(tasks[0], tasks[0]) for _ in tasks],
        "same_prompt_different_reference": [(tasks[0], ref_task) for ref_task in tasks],
        "different_prompt_same_reference": [(prompt_task, tasks[0]) for prompt_task in tasks],
    }
    for group, cases in groups.items():
        for round_index in (1, 2):
            for case_index, (prompt_task, ref_task) in enumerate(cases, 1):
                row = run_case(helper, group, case_index, round_index, prompt_task, ref_task)
                records.append(row)
                print(group, round_index, case_index, row["wall_seconds"], flush=True)
    (OUT / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    deterministic = all(
        len({row["output_sha256"] for row in records
             if row["group"] == group and row["case"] == case_index}) == 1
        for group in groups for case_index in range(1, CASES + 1)
    )
    summary = {
        "run_id": "text-condition-cache-v1",
        "cases_per_group": CASES,
        "rounds": 2,
        "groups": {
            group: {"cold_or_mixed": describe(records, group, 1),
                    "warm": describe(records, group, 2)}
            for group in groups
        },
        "deterministic_across_rounds": deterministic,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
