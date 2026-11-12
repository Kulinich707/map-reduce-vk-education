import os
import duckdb
from common import ROOT, ENDPOINT, BUCKET, KEY


def connect(remote=True):
    connection = duckdb.connect()
    connection.execute("SET threads=2")
    if remote:
        cache = os.getenv("DUCKDB_EXTENSION_DIRECTORY", str(ROOT / ".cache/duckdb"))
        os.makedirs(cache, exist_ok=True)
        connection.execute("SET extension_directory=?", [cache])
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
        for name, value in [
            ("s3_region", "us-east-1"),
            ("s3_url_style", "path"),
            ("s3_endpoint", ENDPOINT.split("://", 1)[1]),
            ("s3_access_key_id", os.getenv("S3_ACCESS_KEY", "labadmin")),
            ("s3_secret_access_key", os.environ["S3_SECRET_KEY"]),
        ]:
            connection.execute(f"SET {name}=?", [value])
        connection.execute("SET s3_use_ssl=false")
    return connection


def calculate(connection, cap, source=None):
    statements = [
        statement.strip()
        for statement in (ROOT / "sql/frequencies.sql").read_text().split(";")
        if statement.strip()
    ]
    connection.execute(statements[0], {"source": source or f"s3://{BUCKET}/{KEY}"})
    connection.execute(statements[1], {"cap": cap})
    return dict(sorted(connection.execute(statements[2]).fetchall()))
