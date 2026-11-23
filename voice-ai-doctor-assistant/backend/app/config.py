"""Centralised configuration.

Everything the app reads from the environment lives here so the rest of the
code never calls ``os.getenv`` directly.  ``APP_MODE`` selects between:

* ``mock`` - no external API keys needed.  A rule-based demo agent drives the
  same tools and the same database as the live agent.
* ``live`` - Pipecat + WebRTC + ElevenLabs STT/TTS + Gemini.  Fails fast at
  start-up if credentials or packages are missing.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


def _load_dotenv() -> None:
    """Load ``backend/.env`` if python-dotenv is installed (it is optional)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is in requirements.txt
        return
    load_dotenv(BACKEND_DIR / ".env", override=False)


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class ConfigError(RuntimeError):
    """Raised when the configuration cannot work (for example live mode without keys)."""


@dataclass(frozen=True)
class Settings:
    app_mode: str = "mock"
    database_path: str = str(BACKEND_DIR / "data" / "clinic.db")
    clinic_name: str = "Meridian Health Clinic"
    cors_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    seed_days: int = 14
    seed_demo_appointments: bool = True
    frontend_dist: str = str(REPO_DIR / "frontend" / "dist")

    # --- live mode ---------------------------------------------------------
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    elevenlabs_stt_model: str = "scribe_v2_realtime"
    stt_language: str = "en"
    google_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.3
    tool_timeout_secs: float = 8.0
    log_level: str = "INFO"

    @property
    def is_live(self) -> bool:
        return self.app_mode == "live"

    def missing_live_requirements(self) -> list[str]:
        """Human-readable list of things live mode still needs."""
        missing: list[str] = []
        if not self.elevenlabs_api_key:
            missing.append("ELEVENLABS_API_KEY (speech-to-text and text-to-speech)")
        if not self.google_api_key:
            missing.append("GOOGLE_API_KEY (Gemini LLM)")
        if importlib.util.find_spec("pipecat") is None:
            missing.append(
                "the pipecat-ai package - run: pip install -r requirements-live.txt"
            )
        return missing

    def validate(self) -> None:
        """Fail fast with an actionable message."""
        if self.app_mode not in {"mock", "live"}:
            raise ConfigError(f"APP_MODE must be 'mock' or 'live', got {self.app_mode!r}.")
        if self.is_live:
            missing = self.missing_live_requirements()
            if missing:
                bullet = "\n  - ".join(missing)
                raise ConfigError(
                    "APP_MODE=live but the following are missing:\n  - "
                    f"{bullet}\nCopy backend/.env.example to backend/.env and fill it in, "
                    "or set APP_MODE=mock to run the demo without credentials."
                )

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        env = os.environ.get
        defaults = cls()
        return cls(
            app_mode=(env("APP_MODE") or "mock").strip().lower(),
            database_path=env("DATABASE_PATH") or defaults.database_path,
            clinic_name=env("CLINIC_NAME") or defaults.clinic_name,
            cors_origins=_list(env("CORS_ORIGINS"), defaults.cors_origins),
            seed_days=max(1, _int(env("SEED_DAYS"), defaults.seed_days)),
            seed_demo_appointments=_bool(env("SEED_DEMO_APPOINTMENTS"), True),
            frontend_dist=env("FRONTEND_DIST") or defaults.frontend_dist,
            elevenlabs_api_key=(env("ELEVENLABS_API_KEY") or "").strip(),
            elevenlabs_voice_id=env("ELEVENLABS_VOICE_ID") or defaults.elevenlabs_voice_id,
            elevenlabs_tts_model=env("ELEVENLABS_TTS_MODEL") or defaults.elevenlabs_tts_model,
            elevenlabs_stt_model=env("ELEVENLABS_STT_MODEL") or defaults.elevenlabs_stt_model,
            stt_language=env("STT_LANGUAGE") or defaults.stt_language,
            google_api_key=(env("GOOGLE_API_KEY") or "").strip(),
            llm_model=env("LLM_MODEL") or defaults.llm_model,
            llm_temperature=float(env("LLM_TEMPERATURE") or defaults.llm_temperature),
            tool_timeout_secs=float(env("TOOL_TIMEOUT_SECS") or defaults.tool_timeout_secs),
            log_level=(env("LOG_LEVEL") or "INFO").upper(),
        )
