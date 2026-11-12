import argparse
import json
import platform
import resource
import time
from common import ROOT, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=["baseline", "combined", "duckdb"])
    parser.add_argument("cap", type=int)
    parser.add_argument("attempt", type=int)
    args = parser.parse_args()
    start = time.perf_counter()

    cpu = time.process_time()
    if args.engine == "duckdb":
        from duckdb_engine import connect, calculate

        result = calculate(connect(), args.cap)
    else:
        from mapreduce import run

        result = run(args.cap, args.engine)
    elapsed = time.perf_counter() - start
    cpu = time.process_time() - cpu
    save(ROOT / f"results/{args.engine}_{args.cap}.json", result)
    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024**2 if platform.system() == "Darwin" else 1024
    )
    stats = {
        "engine": args.engine,
        "cap": args.cap,
        "attempt": args.attempt,
        "seconds": elapsed,
        "cpu_seconds": cpu,
        "peak_rss_mib": peak_rss_mib,
        "groups": len(result),
        "emissions": sum(result.values()),
    }
    save(ROOT / f"logs/profile_{args.engine}_{args.cap}_{args.attempt}.json", stats)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
