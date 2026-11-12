import csv
import json
import tempfile
from pathlib import Path
from collections import Counter
from duckdb_engine import connect, calculate
from mapreduce import batches, mapper


def main():
    fields = [
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

    def r(i, id, title, role, skills):
        return dict(
            zip(
                fields,
                [
                    i,
                    id,
                    title,
                    role,
                    "Москва",
                    "100",
                    "200",
                    "RUR",
                    "false",
                    json.dumps(skills),
                    "2024-01-01",
                    "e",
                    "Нет опыта",
                    "fixture",
                ],
            )
        )

    role = "Программист, разработчик"
    rows = [
        r(1, "a", "PHP\nDeveloper", role, ["PHP", "SQL", " sql "]),
        r(2, "a", "PHP Developer", role, ["PHP", "Redis"]),
        r(3, "b", "Backend", role, ["php", "Git"]),
        r(4, "c", "PHP tester", "Тестировщик", ["PHP"]),
        r(5, "d", "PHP Developer", role, []),
        r(6, "e", "PHPStorm support", role, ["SQL"]),
        r(7, "f", "Backend Developer", role, ["PHP8.2", "SQL"]),
        r(8, "g", "PHP7 Developer", role, ["PHP7"]),
        r(9, "h", "PHPUnit-only support", role, ["PHPUnit"]),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.csv"
        with path.open("w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        for cap in (1, 5, 10, 30):
            connection = connect(False)
            sql_counts = calculate(connection, cap, str(path))
            mapreduce_counts = Counter()
            with path.open(newline="") as csv_file:
                for batch in batches(csv.DictReader(csv_file), 1):
                    mapreduce_counts.update(mapper(batch, cap, True))
            mapreduce_counts = {
                json.dumps(k, ensure_ascii=False, separators=(",", ":")): v
                for k, v in mapreduce_counts.items()
            }
            assert sql_counts == mapreduce_counts
            assert (
                connection.execute("SELECT count(*) FROM population").fetchone()[0] == 5
            )
    print(
        "PASS: 4 caps; dedup; role AND (PHP/version title OR skill); PHPStorm/PHPUnit excluded; multiline CSV; empty/duplicate skills"
    )


if __name__ == "__main__":
    main()
