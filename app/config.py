import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Settings:
    provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()   # "gemini" ou "anthropic"
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    gemini_base_url: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    api_token: str = os.getenv("API_TOKEN", "")
    memory_db: str = os.getenv("MEMORY_DB", str(DATA_DIR / "memory.db"))
    notes_db: str = os.getenv("NOTES_DB", str(DATA_DIR / "notes.db"))
    http_allowed_hosts: list = field(default_factory=lambda: [
        h.strip().lower() for h in os.getenv("HTTP_ALLOWED_HOSTS", "").split(",") if h.strip()])
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    public_mode: bool = os.getenv("PUBLIC_MODE", "false").lower() in ("1", "true", "yes")
    rate_limit_per_min: int = int(os.getenv("RATE_LIMIT_PER_MIN", "15"))
    daily_cap: int = int(os.getenv("DAILY_MESSAGE_CAP", "500"))
    trust_proxy: bool = os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes")
    disabled_tools: list = field(default_factory=lambda: [
        t.strip() for t in os.getenv("DISABLED_TOOLS", "").split(",") if t.strip()])
    max_history: int = 20
    max_tool_rounds: int = 8


settings = Settings()
if settings.public_mode and "send_email" not in settings.disabled_tools:
    settings.disabled_tools.append("send_email")  # jamais d'envoi d'emails depuis un service public
