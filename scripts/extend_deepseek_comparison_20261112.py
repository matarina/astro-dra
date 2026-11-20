"""Extend the frozen writer comparison to four archived feedback questions."""

import argparse
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path

from compare_deepseek_versions_20261112 import OUT, ROOT, digest, run_task, save


CASES = (
    ("kras", "6927b167c196"),
    ("rna", "41d13d68b84e"),
    ("if", "6ac5d65ed736"),
    ("chinese", "90ad0dce1609"),
)
MANIFEST = OUT / "feedback-extension-manifest.json"


def prepare():
    archive = ROOT / "evaluation/archive-prompt-method-candidate-20261112/results"
    inputs = OUT / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    tasks = []
    for name, suffix in CASES:
        files = sorted(archive.glob("*" + suffix + "/traces/**/*writer_request.json.gz"))
        if len(files) != 1:
            raise ValueError((name, len(files)))
        prompt = json.loads(gzip.decompress(files[0].read_bytes()))["prompt"]
        target = inputs / (name + ".txt")
        if target.exists() and target.read_text() != prompt:
            raise ValueError("Existing frozen input differs: " + name)
        target.write_text(prompt)
        tasks.append({
            "id": name,
            "kind": "historical_writer_prompt",
            "source": str(files[0].relative_to(ROOT)),
            "input_sha256": digest(prompt),
            "chars": len(prompt),
        })
    manifest = {
        "scope": "Four additional archived writer-stage prompts, paired official V4.1 Flash versus current gateway; not end-to-end DRA. Prior knowledge and writer contract are part of the frozen input.",
        "controls": {
            "temperature": 0,
            "thinking": {"type": "disabled"},
            "max_tokens": 8192,
            "same_user_message": True,
            "live_retrieval": False,
            "native_review": False,
            "automatic_retry": False,
        },
        "rubric": "feedback-extension-rubric.json",
        "tasks": tasks,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if MANIFEST.exists() and json.loads(MANIFEST.read_text()) != manifest:
        raise ValueError("Existing extension manifest differs")
    save(MANIFEST, manifest)
    return tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--tasks", nargs="+", choices=[name for name, _ in CASES])
    args = parser.parse_args()
    tasks = prepare() if args.prepare else json.loads(MANIFEST.read_text())["tasks"]
    tasks = [task for task in tasks if not args.tasks or task["id"] in args.tasks]
    if not args.run:
        print(json.dumps(tasks, ensure_ascii=False))
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_task, task, provider, "1", 8192)
                   for task in tasks for provider in ("current", "official")]
        for future in concurrent.futures.as_completed(futures):
            future.result()


if __name__ == "__main__":
    main()
