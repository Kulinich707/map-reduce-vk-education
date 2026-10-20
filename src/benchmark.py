import csv
import json
import subprocess
import sys
from statistics import median
from common import ROOT, CAPS, save


def main():
    all_runs = []
    for cap in CAPS:
        for attempt in (1, 2, 3):
            order = ["baseline", "combined", "duckdb"]

            order = order[attempt - 1 :] + order[: attempt - 1]
            for engine in order:
                command = [
                    sys.executable,
                    str(ROOT / "src/profile_worker.py"),
                    engine,
                    str(cap),
                    str(attempt),
                ]
                print("$", " ".join(command), flush=True)
                process = subprocess.run(command, capture_output=True, text=True)
                print(process.stdout, flush=True)
                if process.returncode:
                    print(process.stderr)
                    raise SystemExit(process.returncode)
                all_runs.append(
                    json.loads(
                        (
                            ROOT / f"logs/profile_{engine}_{cap}_{attempt}.json"
                        ).read_text()
                    )
                )
    save(ROOT / "results/profiling_runs.json", all_runs)
    with (ROOT / "results/profiling_runs.csv").open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(all_runs[0]))
        writer.writeheader()
        writer.writerows(all_runs)
    summaries = []

    for cap in CAPS:
        for engine in ("baseline", "combined", "duckdb"):
            matching_runs = [
                run for run in all_runs if run["engine"] == engine and run["cap"] == cap
            ]
            summaries.append(
                {
                    "cap": cap,
                    "engine": engine,
                    "median_seconds": median(run["seconds"] for run in matching_runs),
                    "min_seconds": min(run["seconds"] for run in matching_runs),
                    "max_seconds": max(run["seconds"] for run in matching_runs),
                    "median_peak_rss_mib": median(
                        run["peak_rss_mib"] for run in matching_runs
                    ),
                }
            )
    save(ROOT / "results/profiling_summary.json", summaries)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
