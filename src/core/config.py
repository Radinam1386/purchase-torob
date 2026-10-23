"""Environment configuration with validation at the application boundary."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    llm_reasoning_effort: str
    database_path: Path
    default_lat: float
    default_lng: float
    default_radius_km: float
    max_tool_rounds: int
    timeout_seconds: float
    search_endpoint: str
    search_api_key: str
    geocoding_url: str
    timezone: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            llm_base_url=os.getenv("LLM_BASE_URL", "").rstrip("/"),
            llm_reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "none"),
            database_path=project_path(os.getenv("DB_PATH", "data/torob.sqlite")),
            default_lat=float(os.getenv("DEFAULT_LAT", "35.7219")),
            default_lng=float(os.getenv("DEFAULT_LNG", "51.4097")),
            default_radius_km=float(os.getenv("DEFAULT_RADIUS_KM", "4")),
            max_tool_rounds=int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "8")),
            timeout_seconds=float(os.getenv("AGENT_TIMEOUT_MS", "60000")) / 1000,
            search_endpoint=os.getenv("SEARCH_ENDPOINT", "https://google.serper.dev/search"),
            search_api_key=os.getenv("SEARCH_API_KEY", "").strip(),
            geocoding_url=os.getenv(
                "GEOCODING_URL", "https://nominatim.openstreetmap.org/search"
            ),
            timezone=os.getenv("TZ", "Asia/Tehran"),
        )

    def validate_llm(self) -> None:
        missing = [
            name
            for name, value in (
                ("LLM_API_KEY", self.llm_api_key),
                ("LLM_MODEL", self.llm_model),
                ("LLM_BASE_URL", self.llm_base_url),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"تنظیمات LLM در .env ناقص است: {', '.join(missing)}")


settings = Settings.from_environment()
