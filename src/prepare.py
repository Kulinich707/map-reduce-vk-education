import argparse
import csv
import json
import zipfile
import re
import collections
from datetime import datetime, timezone
from pathlib import Path
from common import ROOT, save, sha

FIELDS = [
    "row_no",
    "id",
    "title",
    "role",
    "area",
    "salary_from",
    "salary_to",
    "currency",
    "gross",
    "skills_json",
    "published_at",
    "employer_id",
    "experience",
    "source",
]


def norm_date(x):
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(x / 1000, timezone.utc).date().isoformat()
    return str(x or "")[:10]


def matches(row):
    return row["role"] == "Программист, разработчик" and (
        bool(re.search(r"\bphp(?:[578](?:\.\d+)*)?\b", row["title"], re.I))
        or any(
            re.fullmatch(r"php(?:[578](?:\.\d+)*)?", salary.strip().lower())
            for salary in json.loads(row["skills_json"])
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--zip", required=True)
    args = parser.parse_args()
    csv.field_size_limit(10000000)
    stats = collections.Counter()
    seen = set()
    variant = []
    regions = collections.Counter()
    currency_counts = collections.Counter()
    source_rows = collections.Counter()
    out = ROOT / "data/all_sources.csv"
    with out.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()

        def emit(row):
            stats["input_rows"] += 1
            row["row_no"] = stats["input_rows"]
            writer.writerow(row)
            source_rows[row["source"]] += 1
            if row["id"] in seen:
                stats["duplicate_id_rows"] += 1
                return
            seen.add(row["id"])
            if matches(row):
                variant.append(row)
                regions[row["area"]] += 1
                currency_counts[(row["currency"], row["gross"])] += 1

        with zipfile.ZipFile(args.zip) as archive:
            members = sorted(
                (
                    i
                    for i in archive.infolist()
                    if not i.is_dir() and i.filename.endswith(".json")
                ),
                key=lambda i: i.filename,
            )
            assert (
                len(members) < 100000
                and sum(i.file_size for i in members) < 2_000_000_000
            )
            for member in members:
                row = json.loads(archive.read(member))
                salary = row.get("salary") or {}
                skills = row.get("key_skills") or []
                skills = [v["name"] if isinstance(v, dict) else v for v in skills]
                roles = [v.get("name", "") for v in row.get("professional_roles", [])]
                role = (
                    "Программист, разработчик"
                    if "Программист, разработчик" in roles
                    else "; ".join(roles)
                )
                emit(
                    dict(
                        row_no=0,
                        id=str(row["vacancy_id"]),
                        title=row.get("name", ""),
                        role=role,
                        area=(row.get("area") or {}).get("name", ""),
                        salary_from=salary.get("from") or "",
                        salary_to=salary.get("to") or "",
                        currency=salary.get("currency") or "",
                        gross=str(salary.get("gross", "")).lower(),
                        skills_json=json.dumps(skills, ensure_ascii=False),
                        published_at=norm_date(row.get("published_at")),
                        employer_id=str(row.get("employer_id") or ""),
                        experience=(row.get("experience") or {}).get("name", ""),
                        source="hh.zip",
                    )
                )
        with open(args.csv, newline="", encoding="utf-8-sig") as csv_file:
            for row in csv.DictReader(csv_file):
                emit(
                    dict(
                        row_no=0,
                        id=row["vacancy_id"],
                        title=row["name"],
                        role=row["role"],
                        area=row["area"],
                        salary_from=row["salary_from"],
                        salary_to=row["salary_to"],
                        currency=row["currency"],
                        gross=row["gross"].lower(),
                        skills_json=json.dumps(
                            [
                                salary.strip()
                                for salary in row["key_skills"].split(";")
                                if salary.strip()
                            ],
                            ensure_ascii=False,
                        ),
                        published_at=norm_date(row["published_at"]),
                        employer_id=row["employer_id"],
                        experience=row["experience"],
                        source="it_vacancies_2024.csv",
                    )
                )
    with (ROOT / "data/php_vacancies.csv").open(
        "w", newline="", encoding="utf-8"
    ) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(variant)
    stats["unique_ids"] = len(seen)
    stats["php_variant5"] = len(variant)
    result = {
        "variant": 5,
        "segment": "Программист, разработчик на PHP",
        "counts": dict(stats),
        "source_rows": dict(source_rows),
        "source_files": [
            {"name": Path(x).name, "bytes": Path(x).stat().st_size, "sha256": sha(x)}
            for x in (args.csv, args.zip)
        ],
        "normalized_bytes": out.stat().st_size,
        "normalized_sha256": sha(out),
        "php_regions": dict(regions.most_common()),
        "php_currency_gross": {str(k): v for k, v in currency_counts.items()},
        "caps": list((5, 10, 30)),
        "precedence": "JSON hh.zip before CSV; deduplicate by vacancy_id before variant filtering",
        "variant_rule": "role exactly Программист, разработчик AND (PHP/PHP5/PHP7/PHP8 with optional minor version in title OR full skill match, case-insensitive)",
        "max_stack": max(
            len(
                set(
                    salary.strip().lower()
                    for salary in json.loads(row["skills_json"])
                    if salary.strip()
                )
            )
            for row in variant
        ),
        "variant_source_distribution": dict(
            collections.Counter(row["source"] for row in variant)
        ),
    }
    save(ROOT / "results/manifest.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
