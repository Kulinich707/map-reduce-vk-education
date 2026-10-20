import csv
import json
import re
import statistics
from collections import Counter
from common import ROOT, save


def main():
    analysis = json.loads((ROOT / "results/analysis.json").read_text())
    verification = json.loads((ROOT / "results/verification.json").read_text())
    rows = []
    seen = set()
    with (ROOT / "data/all_sources.csv").open(newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            skills = {
                re.sub(r"\s+", " ", s.strip().lower())
                for s in json.loads(row["skills_json"])
                if s.strip()
            }
            if row["role"] != "Программист, разработчик" or not (
                re.search(r"\bphp(?:[578](?:\.\d+)*)?\b", row["title"], re.I)
                or any(re.fullmatch(r"php(?:[578](?:\.\d+)*)?", s) for s in skills)
            ):
                continue
            salary = None
            if row["currency"].upper() in ("RUR", "RUB") and row["gross"] == "false":
                bounds = [
                    float(row[k])
                    for k in ("salary_from", "salary_to")
                    if row[k] and float(row[k]) > 0
                ]
                if bounds:
                    salary = sum(bounds) / len(bounds)
            rows.append((row["area"], skills, salary))
    assert (
        len(rows)
        == analysis["population"]["vacancies"]
        == verification["php_population"]
    )
    salaries = [row[2] for row in rows if row[2] is not None]
    assert (
        len(salaries) == analysis["population"]["salary_n"]
        and statistics.median(salaries) == analysis["population"]["median_salary"]
    )
    for region in analysis["selected_regions"]:
        region_rows = [row for row in rows if row[0] == region["area"]]
        assert (
            len(region_rows) == region["vacancies"]
            and statistics.median([row[2] for row in region_rows if row[2] is not None])
            == region["median_salary"]
        )
    regional_counts = {
        group["area"]: Counter(
            s for row in rows if row[0] == group["area"] for s in row[1]
        )
        for group in analysis["selected_regions"]
    }
    checked_skills = 0
    with (ROOT / "results/regional_skill_counts.csv").open(
        newline="", encoding="utf-8"
    ) as csv_file:
        for rec in csv.DictReader(csv_file):
            count = regional_counts[rec["area"]][rec["skill"]]
            total = next(
                group["vacancies"]
                for group in analysis["selected_regions"]
                if group["area"] == rec["area"]
            )
            assert (
                count == int(rec["n"])
                and abs(100 * count / total - float(rec["share_pct"])) <= 0.00501
            )
            checked_skills += 1
    assert checked_skills == sum(len(c) for c in regional_counts.values())
    checked_combinations = 0
    for k in ("2", "3"):
        for direction in ("higher", "lower"):
            for group in analysis["salary_extremes"][k][direction]:
                skills = set(json.loads(group["combo"]))
                yes = [
                    row[2] for row in rows if row[2] is not None and skills <= row[1]
                ]
                no = [
                    row[2]
                    for row in rows
                    if row[2] is not None and not skills <= row[1]
                ]
                assert (
                    len(yes) == group["salary_n"]
                    and statistics.median(yes) == group["median_with"]
                    and statistics.median(no) == group["median_without"]
                )
                checked_combinations += 1
    check = {
        "all_passed": True,
        "php_population": len(rows),
        "salary_n": len(salaries),
        "salary_combinations_checked": checked_combinations,
        "regions_checked": 3,
        "regional_skill_rows_checked": checked_skills,
        "identities_checked": 9,
    }
    save(ROOT / "results/quality.json", check)
    print(json.dumps(check, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
