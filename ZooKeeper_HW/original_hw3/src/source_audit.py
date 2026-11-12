import csv
import json
import collections
from common import ROOT, save


def value(row, key):
    if key == "skills_json":
        return sorted({s.strip().lower() for s in json.loads(row[key])})
    if key in ("salary_from", "salary_to"):
        return float(row[key]) if row[key] else None
    return row[key]


def main():
    archive = {}
    overlap = 0
    field_conflicts = collections.Counter()
    conflict_examples = []
    fields = [
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
    ]
    with (ROOT / "data/all_sources.csv").open(encoding="utf-8", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            if row["source"] == "hh.zip":
                archive[row["id"]] = row
            elif row["id"] in archive:
                overlap += 1
                changed = [
                    k for k in fields if value(row, k) != value(archive[row["id"]], k)
                ]
                field_conflicts.update(changed)
                if changed and len(conflict_examples) < 10:
                    conflict_examples.append(
                        {"id": row["id"], "changed_fields": changed}
                    )
    result = {
        "archive_unique_ids": len(archive),
        "overlap_with_csv": overlap,
        "archive_only": len(archive) - overlap,
        "conflicts_by_field": dict(field_conflicts),
        "sample_conflicts": conflict_examples,
        "precedence": "hh.zip first, before variant filtering",
    }
    save(ROOT / "results/source_audit.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
