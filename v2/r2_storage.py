"""Cloudflare R2 bootstrap for the production LUFCDATA DuckDB."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import boto3
import duckdb
from botocore.client import Config
from botocore.exceptions import ClientError

from .database import DEFAULT_DB_PATH


@dataclass(frozen=True)
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    current_key: str = "football/current.duckdb"

    @classmethod
    def from_env(cls) -> "R2Config":
        values = {
            "account_id": os.environ.get("R2_ACCOUNT_ID"),
            "access_key_id": os.environ.get("R2_ACCESS_KEY_ID"),
            "secret_access_key": os.environ.get("R2_SECRET_ACCESS_KEY"),
            "bucket": os.environ.get("R2_BUCKET"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError("Missing required R2 environment variables: " + ", ".join("R2_" + name.upper() for name in missing))
        return cls(**values, current_key=os.environ.get("R2_CURRENT_KEY", "football/current.duckdb"))

    @property
    def endpoint_url(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


def validate_duckdb(path: str | Path) -> dict[str, int]:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError(f"DuckDB file is missing or empty: {path}")
    conn = duckdb.connect(str(path), read_only=True)
    try:
        existing = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        required = {"seasons", "matches", "player_match_stats", "team_match_stats", "canonical_metric_values"}
        missing = sorted(required - existing)
        if missing:
            raise ValueError("DuckDB missing required tables: " + ", ".join(missing))
        return {
            "matches": int(conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]),
            "player_match_rows": int(conn.execute("SELECT COUNT(*) FROM player_match_stats").fetchone()[0]),
            "team_match_rows": int(conn.execute("SELECT COUNT(*) FROM team_match_stats").fetchone()[0]),
        }
    finally:
        conn.close()


class R2DuckDBStore:
    def __init__(self, config: R2Config | None = None):
        self.config = config or R2Config.from_env()
        self.client = boto3.client(
            "s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def exists(self, key: str | None = None) -> bool:
        key = key or self.config.current_key
        try:
            self.client.head_object(Bucket=self.config.bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def download_current(self, destination: str | Path = DEFAULT_DB_PATH, required: bool = True) -> bool:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not self.exists(self.config.current_key):
            if required:
                raise FileNotFoundError(f"R2 object not found: {self.config.current_key}")
            return False
        with tempfile.NamedTemporaryFile(delete=False, suffix=".duckdb", dir=destination.parent) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self.client.download_file(self.config.bucket, self.config.current_key, str(tmp_path))
            validate_duckdb(tmp_path)
            os.replace(tmp_path, destination)
            return True
        finally:
            tmp_path.unlink(missing_ok=True)
