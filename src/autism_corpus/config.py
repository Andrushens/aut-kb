from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = REPO_ROOT / "cache"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_DATA_DIR = REPO_ROOT / "data"

USER_AGENT = "autism-corpus/1.0 (+contact@yourdomain)"


@dataclass(frozen=True)
class HttpConfig:
    user_agent: str = USER_AGENT
    per_host_rate_per_second: float = 1.0
    cache_ttl_seconds: int = 7 * 24 * 3600
    request_timeout_seconds: float = 30.0
    max_retries: int = 3


@dataclass(frozen=True)
class Settings:
    cache_dir: Path = DEFAULT_CACHE_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    data_dir: Path = DEFAULT_DATA_DIR
    http: HttpConfig = field(default_factory=HttpConfig)
