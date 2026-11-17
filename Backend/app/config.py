import os
from functools import lru_cache
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if it exists
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    """Application configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.app_name: str = "ARRT User Data Extractor"
        self.app_version: str = "1.0.0"

        # External API Configuration
        self.arrt_api_url: str = os.getenv(
            "ARRT_API_URL", "https://www.arrt.org/VerifyCredentials/SearchByName"
        ).strip()
        self.arrt_cookie: str = os.getenv("ARRT_COOKIE", "").strip()
        self.arrt_antiforgery_token: str = os.getenv("ARRT_ANTIFORGERY_TOKEN", "").strip()
        self.arrt_captcha_token: str = os.getenv("ARRT_CAPTCHA_TOKEN", "").strip()

        # Operational Constraints
        raw_concurrency = os.getenv("MAX_CONCURRENCY", "1")
        try:
            self.max_concurrency: int = max(1, min(5, int(raw_concurrency)))
        except ValueError:
            self.max_concurrency = 1

        raw_timeout = os.getenv("REQUEST_TIMEOUT", "60")
        try:
            self.request_timeout: float = float(raw_timeout)
        except ValueError:
            self.request_timeout = 60.0

        raw_retries = os.getenv("MAX_RETRIES", "3")
        try:
            self.max_retries: int = max(0, min(5, int(raw_retries)))
        except ValueError:
            self.max_retries = 3

        raw_backoff = os.getenv("BACKOFF_FACTOR", "1.5")
        try:
            self.backoff_factor: float = float(raw_backoff)
        except ValueError:
            self.backoff_factor = 1.5

        # Storage
        self.exports_dir: Path = BASE_DIR / os.getenv("EXPORTS_DIR", "exports")
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def parse_cookie_string(self) -> Dict[str, str]:
        """
        Parses raw Cookie header string into a key-value dictionary.
        Handles semicolon-separated cookie strings e.g.:
        "ASP.NET_SessionId=xyz; __RequestVerificationToken=abc"
        """
        cookies: Dict[str, str] = {}
        if not self.arrt_cookie:
            return cookies

        pairs = self.arrt_cookie.split(";")
        for pair in pairs:
            if "=" in pair:
                key, val = pair.split("=", 1)
                key = key.strip()
                val = val.strip()
                if key:
                    cookies[key] = val
        return cookies

    def is_auth_configured(self) -> bool:
        """Returns True if minimum required tokens/cookies are configured."""
        return bool(self.arrt_captcha_token)


@lru_cache()
def get_settings() -> Settings:
    """Returns a cached instance of application settings."""
    return Settings()

