import csv
import json
import re
import math
import statistics
import hashlib
from collections import Counter
from common import ROOT, CAPS, save


def main():
    seen = set()
    rows = []
    with (ROOT / "data/all_sources.csv").open(newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            skills = sorted(
                {
                    re.sub(r"\s+", " ", s.strip().lower())
                    for s in json.loads(row["skills_json"])
                    if s.strip()
                }
            )
            if row["role"] != "Программист, разработчик" or not (
                re.search(r"\bphp(?:[578](?:\.\d+)*)?\b", row["title"], re.I)
                or any(re.fullmatch(r"php(?:[578](?:\.\d+)*)?", s) for s in skills)
            ):
                continue
            row["skills"] = skills
            rows.append(row)
    checks = []
    for cap in CAPS:
        payloads = [
            json.loads((ROOT / f"results/{engine}_{cap}.json").read_text())
            for engine in ("baseline", "combined", "duckdb")
        ]
        assert payloads[0] == payloads[1] == payloads[2]
        groups = {}
        for k in (1, 2, 3):
            frequencies = {
                key: count
                for key, count in payloads[0].items()
                if len(json.loads(key)) == k
            }
            expected = sum(
                math.comb(min(len(row["skills"]), cap), k)
                for row in rows
                if min(len(row["skills"]), cap) >= k
            )
            assert sum(frequencies.values()) == expected
            groups[str(k)] = {
                "unique": len(frequencies),
                "total": sum(frequencies.values()),
                "expected": expected,
                "top10": sorted(frequencies.items(), key=lambda t: (-t[1], t[0]))[:10],
            }
        digest = hashlib.sha256(
            json.dumps(payloads[0], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        checks.append(
            {"cap": cap, "all_keys_equal": True, "sha256": digest, "counts": groups}
        )
    save(
        ROOT / "results/verification.json",
        {"php_population": len(rows), "checks": checks, "all_passed": True},
    )
    print(
        json.dumps(
            {
                "population": len(rows),
                "all_keys_equal": True,
                "combinatorial_identities_checked": 9,
                "caps": list(CAPS),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
