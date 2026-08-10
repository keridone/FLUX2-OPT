import os
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")

from huggingface_hub import hf_hub_download


TARGET = Path(r"E:\flux\sdcpp\models")
JOBS = [
    ("leejet/FLUX.2-klein-4B-GGUF", "flux-2-klein-4b-Q8_0.gguf"),
    ("unsloth/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf"),
    ("Comfy-Org/flux2-dev", "split_files/vae/flux2-vae.safetensors"),
]


def download(repo_id: str, filename: str) -> None:
    expected = TARGET / filename
    for attempt in range(1, 101):
        try:
            print(f"DOWNLOAD {filename} attempt={attempt}", flush=True)
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=TARGET,
                force_download=False,
            )
            size = Path(path).stat().st_size
            print(f"DONE {path} bytes={size}", flush=True)
            return
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"RETRY {filename}: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(min(attempt, 10))
    raise RuntimeError(f"download failed after 100 attempts: {expected}")


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for repo_id, filename in JOBS:
        download(repo_id, filename)


if __name__ == "__main__":
    main()
