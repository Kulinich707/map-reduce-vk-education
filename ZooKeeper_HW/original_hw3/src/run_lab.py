import argparse
import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def step(label, script, *args):
    command = [sys.executable, str(ROOT / "src" / script), *map(str, args)]
    with (ROOT / "logs" / f"{label}.txt").open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n")
        log.flush()
        process = subprocess.Popen(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        if process.wait():
            raise SystemExit(f"Failed: {label}; inspect logs/{label}.txt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="Путь к исходному CSV вакансий")
    parser.add_argument("--zip", help="Путь к архиву JSON-вакансий")
    parser.add_argument(
        "--prepared",
        action="store_true",
        help="Использовать готовый data/all_sources.csv",
    )
    parser.add_argument("--reuse-container", help="Имя существующего контейнера RustFS")
    args = parser.parse_args()
    if args.reuse_container:

        docker = (
            shutil.which("docker")
            or "/Applications/Docker.app/Contents/Resources/bin/docker"
        )
        import json

        environment_entries = json.loads(
            subprocess.check_output(
                [
                    docker,
                    "inspect",
                    args.reuse_container,
                    "--format",
                    "{{json .Config.Env}}",
                ],
                text=True,
            )
        )
        container_settings = dict(
            x.split("=", 1) for x in environment_entries if "=" in x
        )
        os.environ["S3_ACCESS_KEY"] = container_settings["RUSTFS_ACCESS_KEY"]
        os.environ["S3_SECRET_KEY"] = container_settings["RUSTFS_SECRET_KEY"]
    if not args.prepared:
        if not args.csv or not args.zip:
            parser.error("Укажите --csv и --zip или используйте --prepared")
        step("01_prepare", "prepare.py", "--csv", args.csv, "--zip", args.zip)
    step("01b_source_audit", "source_audit.py")
    step("02_storage", "storage.py", "input")
    step("03_edge_cases", "edge_cases.py")
    step("04_benchmark", "benchmark.py")
    step("05_verify", "verify.py")
    step("06_analysis", "analyze.py")
    step("07_quality", "quality.py")
    step("08_upload_results", "storage.py", "results")
    step("09_s3_audit", "storage.py", "audit")


if __name__ == "__main__":
    main()
