import json
import os
import hashlib
from pathlib import Path
import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
CAPS = (5, 10, 30)
BUCKET = "hh-lake"
PREFIX = "variant5-php"
KEY = PREFIX + "/input/all_sources.csv"
ENDPOINT = os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000")


def client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY", "labadmin"),
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()
