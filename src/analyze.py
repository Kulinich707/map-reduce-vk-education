import csv
import json
import collections
from statistics import median
from common import ROOT, save
from duckdb_engine import connect, calculate


def export(connection, sql, name, params=None):
    cursor = connection.execute(sql, params or [])
    fields = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    with (ROOT / "results" / f"{name}.csv").open(
        "w", encoding="utf-8", newline=""
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(fields)
        writer.writerows(rows)
    return [dict(zip(fields, row)) for row in rows]


def weighted_median(histogram):
    n = sum(histogram.values())
    targets = ((n - 1) // 2, n // 2)
    values = []
    seen = 0
    for value, count in sorted(histogram.items()):
        if count <= 0:
            continue
        for target in targets:
            if seen <= target < seen + count:
                values.append(value)
        seen += count
    return sum(values) / 2 if values else None


def main():
    connection = connect()
    calculate(connection, 30)
    population = export(
        connection,
        """SELECT count(*) vacancies,count(salary) salary_n,median(salary) median_salary,
 min(salary) min_salary,max(salary) max_salary,count(*) FILTER(WHERE len(skills)=0) no_skills,
 max(len(skills)) max_stack,min(published_at) min_date,max(published_at) max_date,
 count(*) FILTER(WHERE try_cast(salary_from AS DOUBLE)>try_cast(salary_to AS DOUBLE)) inverted_bounds
 FROM population""",
        "population",
    )[0]
    population["salary_low_n"] = connection.execute(
        "SELECT count(*) FROM population WHERE salary<10000"
    ).fetchone()[0]
    population["median_salary_without_low"] = connection.execute(
        "SELECT median(salary) FROM population WHERE salary>=10000"
    ).fetchone()[0]
    population["with_title_php"] = connection.execute(
        "SELECT count(*) FROM population WHERE regexp_matches(title,'\\bphp(?:[578](?:\\.[0-9]+)*)?\\b','i')"
    ).fetchone()[0]
    population["skill_only_php"] = (
        population["vacancies"] - population["with_title_php"]
    )
    regions = export(
        connection,
        """SELECT area,count(*) vacancies,count(salary) salary_n,
 round(100.0*count(salary)/count(*),2) salary_coverage_pct,median(salary) median_salary,
 quantile_cont(salary,0.25) q1,quantile_cont(salary,0.75) q3,avg(len(skills)) avg_stack
 FROM population GROUP BY area ORDER BY vacancies DESC,area""",
        "regions_all",
    )
    chosen = regions[:3]
    assert len(chosen) == 3 and all(row["salary_n"] >= 10 for row in chosen)
    export(
        connection,
        """SELECT p.area,l.skill,count(*) n,round(100.0*count(*)/max(t.total),2) share_pct
 FROM skills_long l JOIN population p USING(id)
 JOIN (SELECT area,count(*) total FROM population GROUP BY area) t USING(area)
 WHERE p.area IN (SELECT area FROM population GROUP BY area ORDER BY count(*) DESC,area LIMIT 3)
 GROUP BY p.area,l.skill ORDER BY p.area,n DESC,l.skill""",
        "regional_skill_counts",
    )
    export(
        connection,
        """SELECT * FROM (SELECT *,row_number() OVER(PARTITION BY area ORDER BY n DESC,skill) rk
 FROM read_csv_auto(?)) WHERE rk<=10 ORDER BY area,rk""",
        "regional_skills_top10",
        [str(ROOT / "results/regional_skill_counts.csv")],
    )

    connection.execute("""CREATE TEMP TABLE memberships AS
 SELECT a.id,to_json(list_value(a.skill,b.skill))::VARCHAR AS combo,2 AS k
 FROM skills_long a JOIN skills_long b ON a.id=b.id AND a.skill<b.skill
 UNION ALL
 SELECT a.id,to_json(list_value(a.skill,b.skill,c.skill))::VARCHAR,3
 FROM skills_long a JOIN skills_long b ON a.id=b.id AND a.skill<b.skill
 JOIN skills_long c ON a.id=c.id AND b.skill<c.skill""")
    grouped = export(
        connection,
        """SELECT m.combo,m.k,count(*) support,count(p.salary) salary_n,
 median(p.salary) median_with,quantile_cont(p.salary,0.25) q1,quantile_cont(p.salary,0.75) q3
 FROM memberships m JOIN population p USING(id) GROUP BY m.combo,m.k HAVING count(p.salary)>=10""",
        "salary_grouped",
    )
    global_hist = dict(
        connection.execute(
            "SELECT salary,count(*) FROM population WHERE salary IS NOT NULL GROUP BY salary"
        ).fetchall()
    )
    salary_histograms = collections.defaultdict(dict)
    for combo, salary, count in connection.execute(
        "SELECT m.combo,p.salary,count(*) FROM memberships m JOIN population p USING(id) WHERE p.salary IS NOT NULL GROUP BY m.combo,p.salary"
    ).fetchall():
        salary_histograms[combo][salary] = count
    for row in grouped:
        without = {
            salary: n - salary_histograms[row["combo"]].get(salary, 0)
            for salary, n in global_hist.items()
        }
        row["median_without"] = weighted_median(without)
        row["without_n"] = sum(without.values())
        row["delta"] = (
            row["median_with"] - row["median_without"]
            if row["median_without"]
            else None
        )
        row["uplift_pct"] = (
            (row["median_with"] / row["median_without"] - 1) * 100
            if row["median_without"]
            else None
        )
    grouped = [
        row for row in grouped if row["median_without"] and row["median_without"] > 0
    ]
    grouped.sort(key=lambda row: (row["k"], -row["uplift_pct"], row["combo"]))
    with (ROOT / "results/salary_associations.csv").open(
        "w", newline="", encoding="utf-8"
    ) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(grouped[0]))
        writer.writeheader()
        writer.writerows(grouped)

    def extremes(threshold):
        return {
            str(k): {
                "higher": sorted(
                    [
                        row
                        for row in grouped
                        if row["k"] == k and row["salary_n"] >= threshold
                    ],
                    key=lambda x: (-x["uplift_pct"], x["combo"]),
                )[:5],
                "lower": sorted(
                    [
                        row
                        for row in grouped
                        if row["k"] == k and row["salary_n"] >= threshold
                    ],
                    key=lambda x: (x["uplift_pct"], x["combo"]),
                )[:5],
            }
            for k in (2, 3)
        }

    salary_extremes = extremes(10)
    robust = extremes(30)
    employers = []
    for k in (2, 3):
        for direction in ("higher", "lower"):
            top = salary_extremes[str(k)][direction][0]
            employer_rows = export(
                connection,
                """SELECT p.employer_id,count(*) n FROM population p JOIN memberships m USING(id)
    WHERE m.combo=? AND p.salary IS NOT NULL GROUP BY p.employer_id ORDER BY n DESC,p.employer_id""",
                f"employers_{k}_{direction}",
                [top["combo"]],
            )
            employers.append(
                {
                    "combo": top["combo"],
                    "k": k,
                    "direction": direction,
                    "employers": employer_rows,
                }
            )

    export(
        connection,
        """SELECT experience,count(*) n,count(salary) salary_n,median(salary) median_salary
 FROM population GROUP BY experience ORDER BY n DESC""",
        "experience",
    )
    analysis = {
        "population": population,
        "selected_regions": chosen,
        "salary_extremes": salary_extremes,
        "robust_support30": robust,
        "employer_checks": employers,
        "salary_min_support": 10,
        "salary_eligible_groups": len(grouped),
    }
    save(ROOT / "results/analysis.json", analysis)
    print(
        json.dumps(
            {
                "population": population,
                "selected_regions": chosen,
                "salary_eligible_groups": len(grouped),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
