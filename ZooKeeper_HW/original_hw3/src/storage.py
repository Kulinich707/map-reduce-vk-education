import argparse
import json
import hashlib
from common import ROOT, BUCKET, PREFIX, KEY, client, save, sha, CAPS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["input", "results", "audit"])
    args = parser.parse_args()
    s3 = client()
    if BUCKET not in [b["Name"] for b in s3.list_buckets()["Buckets"]]:
        s3.create_bucket(Bucket=BUCKET)
    if args.action == "input":
        for name in ("all_sources.csv", "php_vacancies.csv"):
            key = PREFIX + "/input/" + name
            path = ROOT / "data" / name
            s3.upload_file(str(path), BUCKET, key)
            body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
            digest = hashlib.sha256()
            for block in iter(lambda: body.read(1024 * 1024), b""):
                digest.update(block)
            body.close()
            assert digest.hexdigest() == sha(path)
            print(
                "PUT/GET SHA256 OK",
                f"s3://{BUCKET}/{key}",
                path.stat().st_size,
                digest.hexdigest(),
            )
    elif args.action == "results":
        for path in sorted((ROOT / "results").iterdir()):
            if path.is_file():
                s3.upload_file(str(path), BUCKET, PREFIX + "/results/" + path.name)
    else:
        objects = []
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=BUCKET, Prefix=PREFIX + "/"
        ):
            for stored_object in page.get("Contents", []):
                objects.append(
                    {"key": stored_object["Key"], "bytes": stored_object["Size"]}
                )
        checks = []
        for engine in ("baseline", "combined", "duckdb"):
            for cap in CAPS:
                path = ROOT / f"results/{engine}_{cap}.json"
                key = PREFIX + "/results/" + path.name
                body = s3.get_object(Bucket=BUCKET, Key=key)["Body"]
                digest = hashlib.sha256()
                for block in iter(lambda: body.read(1024 * 1024), b""):
                    digest.update(block)
                body.close()
                assert digest.hexdigest() == sha(path)
                checks.append(key)
        save(
            ROOT / "results/s3_audit.json",
            {
                "objects": objects,
                "nine_results_identical": True,
                "checked_keys": checks,
            },
        )
        print(
            json.dumps(
                {"objects": objects, "nine_results_identical": True},
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
