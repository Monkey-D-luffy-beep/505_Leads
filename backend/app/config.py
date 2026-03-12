import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


class Settings:
    # Supabase
    SUPABASE_URL: str = _env("SUPABASE_URL")
    SUPABASE_ANON_KEY: str = _env("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_KEY: str = _env("SUPABASE_SERVICE_KEY")

    # Hunter.io
    HUNTER_API_KEY: str = _env("HUNTER_API_KEY")

    # Brevo (Sendinblue)
    BREVO_API_KEY: str = _env("BREVO_API_KEY")
    BREVO_SMTP_HOST: str = _env("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
    BREVO_SMTP_PORT: int = int(_env("BREVO_SMTP_PORT", "587"))
    BREVO_SENDER_EMAIL: str = _env("BREVO_SENDER_EMAIL")
    BREVO_SENDER_NAME: str = _env("BREVO_SENDER_NAME")

    # Redis (Upstash)
    REDIS_URL: str = _env("REDIS_URL")

    # IMAP (for reply polling)
    IMAP_HOST: str = _env("IMAP_HOST")
    IMAP_PORT: int = int(_env("IMAP_PORT", "993"))
    IMAP_USER: str = _env("IMAP_USER")
    IMAP_PASSWORD: str = _env("IMAP_PASSWORD")

    # App
    SECRET_KEY: str = _env("SECRET_KEY", "change-me")
    ENVIRONMENT: str = _env("ENVIRONMENT", "development")
    FRONTEND_URL: str = _env("FRONTEND_URL", "http://localhost:5173")
    BACKEND_URL: str = _env("BACKEND_URL", "http://localhost:8000")


settings = Settings()
