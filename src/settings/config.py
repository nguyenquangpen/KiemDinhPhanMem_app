# get environment variables for configuration
import os
import sys
from dotenv import load_dotenv

try:
    from src.utils import resource_path
except ModuleNotFoundError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.abspath(os.path.join(current_dir, ".."))
    if src_dir not in sys.path:
        sys.path.append(src_dir)
    from utils import resource_path

env_path = resource_path('.env')


# Load environment variables from .env file
load_dotenv()

# Get environment variables with default values
API_ENDPOINT = os.getenv("API_ENDPOINT", "http://localhost:8765")
WS_ENDPOINT = os.getenv("WS_ENDPOINT", "ws://localhost:8765")
# App không có màn hình đăng nhập: tự đăng nhập server bằng tài khoản này (chưa có thì tự đăng ký)
DEMO_USERNAME = os.getenv("DEMO_USERNAME", "demo")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo123456")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
TIMEZONE = os.getenv("TIMEZONE", "UTC").strip('"')  # Remove quotes if present

# Validate LOG_LEVEL
VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
if LOG_LEVEL not in VALID_LOG_LEVELS:
    print(f"Warning: Invalid LOG_LEVEL '{LOG_LEVEL}'. Using default 'INFO'.")
    LOG_LEVEL = "INFO"
if ENVIRONMENT not in ["development", "production", "testing"]:
    print(f"Warning: Invalid ENVIRONMENT '{ENVIRONMENT}'. Using default 'development'.")
    ENVIRONMENT = "development"

if ENVIRONMENT == "production":
    # In production, we might want to set stricter logging levels
    LOG_LEVEL = "ERROR"


# Get the API endpoint from environment variables
if not API_ENDPOINT:
    raise ValueError("API_ENDPOINT environment variable is not set.")
