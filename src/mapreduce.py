import csv, io, json, itertools, re
from collections import Counter
from common import client, BUCKET, KEY


def matches(row):
    if row["role"] != "Программист, разработчик":
        return False
    return bool(re.search(r"\bphp(?:[578](?:\.\d+)*)?\b", row["title"], re.I)) or any(
        re.fullmatch(r"php(?:[578](?:\.\d+)*)?", s.strip().lower())
        for s in json.loads(row["skills_json"])
    )


def batches(reader, size=100):
    seen = set()
    batch = []
    for row in reader:

        if row["id"] in seen:
            continue
        seen.add(row["id"])
        if not matches(row):
            continue
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def mapper(rows, cap, combine):
    result = Counter() if combine else []
    for row in rows:
        skills = sorted(
            {
                re.sub(r"\s+", " ", skill.strip().lower())
                for skill in json.loads(row["skills_json"])
                if skill.strip()
            }
        )[:cap]
        for combination_size in (1, 2, 3):
            for combo in itertools.combinations(skills, combination_size):
                if combine:

                    result[combo] += 1
                else:
                    result.append(
                        json.dumps(combo, ensure_ascii=False, separators=(",", ":"))
                    )
    return result


def run(cap, mode):
    body = client().get_object(Bucket=BUCKET, Key=KEY)["Body"]

    reader = csv.DictReader(io.TextIOWrapper(body, encoding="utf-8", newline=""))
    reduced = Counter()
    if mode == "baseline":
        emissions = []
        for batch in batches(reader):
            emissions.extend(mapper(batch, cap, False))
        reduced.update(emissions)
    else:
        for batch in batches(reader):
            reduced.update(mapper(batch, cap, True))

        reduced = {
            json.dumps(combo, ensure_ascii=False, separators=(",", ":")): count
            for combo, count in reduced.items()
        }
    body.close()
    return dict(sorted(reduced.items()))
