import os

from app_distribution_server.logger import logger
from typing import Optional

STORAGE_URL = os.getenv("STORAGE_URL", "osfs://./uploads")

UPLOADS_SECRET_AUTH_TOKEN = os.getenv("UPLOADS_SECRET_AUTH_TOKEN")

if not UPLOADS_SECRET_AUTH_TOKEN:
    UPLOADS_SECRET_AUTH_TOKEN = "mysecretpassword"  # noqa: S105
    logger.warn(
        "SECURITY WARNING: Using default auth token!"
        " For security reasons override it with the 'UPLOADS_SECRET_AUTH_TOKEN' env var.",
    )

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
APP_VERSION = os.getenv("APP_VERSION") or "0.0.1-development"
APP_TITLE = "Appsyra"

_raw_logo_url = os.getenv("LOGO_URL", "/static/logo.png")
LOGO_URL: Optional[str] = None if _raw_logo_url.lower() in ["", "0", "false"] else _raw_logo_url

COMPANY_NAME = "Appsyra"


def get_absolute_url(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"

    return f"{APP_BASE_URL}{path}"
