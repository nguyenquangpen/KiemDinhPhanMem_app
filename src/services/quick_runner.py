"""
Runner cố định cho testcase nhập liệu form: dùng locator đã chọn để điền field, bấm Submit,
thu kết quả trên trang rồi gọi server /api/judge (1 lần gọi LLM, input nhỏ) để chấm OK/NG.
Không cần agent LLM duyệt DOM từng bước.
"""
import base64
import json
import re
from datetime import datetime
from typing import Dict, List, Optional

import httpx
from playwright.async_api import Locator, Page, async_playwright

from services.field_locators import TEST_BROWSER_PROFILE
from services.logging_config import get_logger

logger = get_logger(__name__)

# Thông báo lỗi / alert / toast hay gặp ở các UI framework phổ biến
_COLLECT_MESSAGES_JS = r"""
() => {
  const out = [];
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  document.querySelectorAll('input,textarea,select').forEach((el) => {
    const name = el.name || el.id || el.placeholder || el.tagName.toLowerCase();
    if (el.validationMessage) out.push(`${name}: ${el.validationMessage}`);
    else if (el.getAttribute('aria-invalid') === 'true') out.push(`${name}: aria-invalid`);
  });
  const sel = '[role=alert],[role=status],[aria-live],.error,.errors,.invalid-feedback,.help-block,' +
    '[class*="error"],[class*="Error"],[class*="toast"],[class*="alert"],[class*="message"],[class*="notification"]';
  document.querySelectorAll(sel).forEach((el) => {
    const t = (el.innerText || '').trim();
    if (t && t.length < 300 && visible(el)) out.push(t);
  });
  return [...new Set(out)].slice(0, 20);
}
"""


def parse_reference(reference, field_names: List[str]) -> Dict[str, str]:
    """`test_reference` -> {field: value}. Nhận JSON object (định dạng mới) hoặc chuỗi cũ 'A: x, B: y'."""
    by_lower = {n.lower(): n for n in field_names}

    def normalize(data: Dict) -> Dict[str, str]:
        return {by_lower.get(str(k).lower(), str(k)): "" if v is None else str(v) for k, v in data.items()}

    if isinstance(reference, dict):
        return normalize(reference)
    reference = str(reference or "")
    try:
        data = json.loads(reference)
        if isinstance(data, dict):
            return normalize(data)
    except json.JSONDecodeError:
        pass

    # Định dạng cũ: tách theo vị trí "<tên field>:" đã biết, để giá trị chứa dấu phẩy không bị cắt sai
    marks = []
    for name in field_names:
        match = re.search(rf"{re.escape(name)}\s*:", reference, re.IGNORECASE)
        if match:
            marks.append((match.start(), match.end(), name))
    marks.sort()
    values = {}
    for i, (_, end, name) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(reference)
        values[name] = reference[end:stop].strip().rstrip(",;").strip()
    return values


async def resolve(page: Page, locator: Dict) -> Optional[Locator]:
    """Thử lần lượt các cách định vị đã lưu, lấy cái đầu tiên tìm thấy phần tử đang hiển thị."""
    for cand in locator.get("candidates", []):
        by, value = cand.get("by"), cand.get("value")
        try:
            if by == "css":
                loc = page.locator(value)
            elif by == "label":
                loc = page.get_by_label(value, exact=True)
            elif by == "placeholder":
                loc = page.get_by_placeholder(value, exact=True)
            elif by == "text":
                loc = page.get_by_role("button", name=value, exact=True)
                if await loc.count() == 0:
                    loc = page.get_by_text(value, exact=True)
            elif by == "xpath":
                loc = page.locator(f"xpath={value}")
            else:
                continue
            if await loc.count() > 0 and await loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


async def fill_value(element: Locator, locator: Dict, value: str):
    tag, input_type = locator.get("tag", ""), (locator.get("type") or "").lower()
    if tag == "select":
        try:
            await element.select_option(label=value)
        except Exception:
            await element.select_option(value=value)
    elif input_type in ("checkbox", "radio"):
        if value.strip().lower() in ("", "false", "0", "no", "off"):
            await element.uncheck()
        else:
            await element.check()
    else:
        await element.fill(value)


async def _screenshot(page: Page) -> str:
    return base64.b64encode(await page.screenshot(full_page=True)).decode()


async def run_quick_testcase(
    test_case: Dict,
    task: Dict,
    locators: Dict,
    api_endpoint: str,
    auth_token: Optional[str],
    headless: bool = False,
) -> Dict:
    test_id = str(test_case.get("uuid", "unknown"))
    result = {
        "test_id": test_id,
        "test_name": test_case.get("test_case", "Unknown Test"),
        "status": "error",
        "start_time": datetime.now().isoformat(),
        "screenshots": [],
        "errors": [],
        "step_number": 0,
        "quick_run": True,
    }
    fields: Dict[str, Dict] = locators["fields"]
    values = parse_reference(test_case.get("test_reference"), list(fields))
    # Field bắt buộc mà testcase không ghi giá trị -> dùng default value của spec
    for item in task.get("items", []):
        name = item.get("item_name")
        if name in fields and name not in values and item.get("required") and item.get("default"):
            values[name] = str(item["default"])

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                TEST_BROWSER_PROFILE, headless=headless, no_viewport=True, args=["--start-maximized"]
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(task.get("url_test") or "")
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                filled = {}
                for name, value in values.items():
                    if name not in fields:
                        continue
                    element = await resolve(page, fields[name])
                    if element is None:
                        result["errors"].append(f"Không tìm thấy field '{name}' trên trang - hãy chọn lại field")
                        continue
                    await fill_value(element, fields[name], value)
                    filled[name] = value
                result["screenshots"].append(await _screenshot(page))

                url_before = page.url
                submit = locators.get("submit")
                if submit:
                    button = await resolve(page, submit)
                    if button is None:
                        result["errors"].append("Không tìm thấy nút Submit trên trang - hãy chọn lại")
                    else:
                        await button.click()
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(1000)  # chờ validate / toast hiện ra

                messages = await page.evaluate(_COLLECT_MESSAGES_JS)
                page_text = (await page.inner_text("body"))[:1500]
                url_after = page.url
                result["screenshots"].append(await _screenshot(page))
            finally:
                await context.close()

        if result["errors"]:
            result["error_message"] = "; ".join(result["errors"])
            return result

        verdict = await _judge(api_endpoint, auth_token, {
            "test_field": test_case.get("test_field", ""),
            "test_case": test_case.get("test_case", ""),
            "test_expect": test_case.get("test_expect", ""),
            "filled_values": filled,
            "url_before": url_before,
            "url_after": url_after,
            "messages": messages,
            "page_text": page_text,
        })
        result["status"] = "passed" if verdict["result"] else "failed"
        result["action_result"] = verdict["reason"]
        if not verdict["result"]:
            result["error_message"] = verdict["reason"]
    except Exception as e:
        logger.error("Quick run failed for %s: %s", test_id, e, exc_info=True)
        result["error"] = str(e)
        result["error_message"] = str(e)
        result["errors"].append(str(e))
    finally:
        result["end_time"] = datetime.now().isoformat()
    return result


async def _judge(api_endpoint: str, auth_token: Optional[str], payload: Dict) -> Dict:
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
    # Server chấm qua ChatGPT Web nên có thể mất vài chục giây
    async with httpx.AsyncClient(timeout=600) as client:
        response = await client.post(f"{api_endpoint}/api/judge", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()
