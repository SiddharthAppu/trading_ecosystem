import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory for the monorepo structure
# If running from service subfolder, go up to `consolidated_platform`
BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
AUTH_DIR = CONFIG_DIR / "auth"
ENV_FILE = CONFIG_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

DB_URL = os.getenv("DATABASE_URL")
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
UPSTOX_CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID")

class ProjectPaths:
    ROOT = BASE_DIR
    CONFIG = CONFIG_DIR
    AUTH = AUTH_DIR
    CORE = BASE_DIR / "packages" / "trading_core"
    SERVICES = BASE_DIR / "services"
    APPS = BASE_DIR / "apps"

def get_auth_file(filename: str) -> str:
    return str(AUTH_DIR / filename)
