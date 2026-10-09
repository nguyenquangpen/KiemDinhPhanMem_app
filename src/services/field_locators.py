"""
Lưu locator của các field đã chọn trên trang (theo task) vào file JSON cạnh app.

Cấu trúc file:
{
  "<task_id>": {
    "fields": {"<item name>": {"desc": "...", "candidates": [{"by": "css", "value": "#username"}, ...]}},
    "submit": {"desc": "...", "candidates": [...]}
  }
}
"""
import json
import os
from typing import Dict, Optional

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOCATORS_FILE = os.path.join(APP_ROOT, "field_locators.json")
# Profile trình duyệt dùng chung cho chọn field và chạy test: đăng nhập web cần test 1 lần là giữ session
TEST_BROWSER_PROFILE = os.path.join(APP_ROOT, ".test_browser_profile")


def _load_all() -> Dict:
    if not os.path.exists(LOCATORS_FILE):
        return {}
    with open(LOCATORS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_task_locators(task_id: str) -> Optional[Dict]:
    """Trả về locator của task, None nếu task chưa chọn field nào."""
    data = _load_all().get(str(task_id))
    if not data or not data.get("fields"):
        return None
    return data


def save_task_locators(task_id: str, fields: Dict[str, Dict], submit: Optional[Dict]):
    data = _load_all()
    data[str(task_id)] = {"fields": fields, "submit": submit}
    with open(LOCATORS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
