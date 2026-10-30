from dataclasses import dataclass
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

APP_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = APP_ROOT / ".data"
    join_code: str = ""
    hermes_url: str = "http://127.0.0.1:8642"
    hermes_key: str = ""
    hermes_model: str = "hermes-agent"
    hermes_reasoning_effort: str | None = None
    hermes_timeout: float = 90
    public_origin: str = "http://127.0.0.1:7340"
    secure_cookies: bool = False
    session_seconds: int = 604800

    def __post_init__(self):
        if self.hermes_reasoning_effort not in (None,'low','medium','high','xhigh','max'):raise ValueError('Choose a supported reasoning effort')
        root = self.data_dir.resolve()
        # All writes belong to this application, even when launched elsewhere.
        if not root.is_relative_to(APP_ROOT) or root == APP_ROOT:
            raise ValueError("RESIDENCY_DATA_DIR must be a subdirectory of residency_app")
        object.__setattr__(self, "data_dir", root)
        if len(self.join_code) < 12:
            raise ValueError("Set RESIDENCY_JOIN_CODE to at least 12 characters")
        for label, value in (("HERMES_API_URL", self.hermes_url), ("RESIDENCY_ORIGIN", self.public_origin)):
            parsed = urlsplit(value)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise ValueError(f"{label} must be an HTTP(S) URL without credentials, query, or fragment")
            if label == "RESIDENCY_ORIGIN" and parsed.path not in ("", "/"):
                raise ValueError("RESIDENCY_ORIGIN must not contain a path")
        if not math.isfinite(self.hermes_timeout) or not 0 < self.hermes_timeout <= 600:
            raise ValueError("HERMES_TIMEOUT must be between 0 and 600 seconds")
        if self.public_origin.startswith("https:") and not self.secure_cookies:
            raise ValueError("HTTPS requires RESIDENCY_SECURE_COOKIES=true")

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(os.environ.get("RESIDENCY_DATA_DIR", APP_ROOT / ".data")),
            join_code=os.environ.get("RESIDENCY_JOIN_CODE", ""),
            hermes_url=os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642").rstrip("/"),
            hermes_key=os.environ.get("HERMES_API_KEY", ""),
            hermes_model=os.environ.get("HERMES_MODEL", "hermes-agent"),
            hermes_timeout=float(os.environ.get("HERMES_TIMEOUT", "90")),
            public_origin=os.environ.get("RESIDENCY_ORIGIN", "http://127.0.0.1:7340").rstrip("/"),
            secure_cookies=os.environ.get("RESIDENCY_SECURE_COOKIES", "false").lower() == "true",
        )
