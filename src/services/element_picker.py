"""
Mở trang cần test và cho người dùng click lần lượt từng field (1, 2, 3...) + nút Submit.
Mỗi lần click lưu nhiều cách định vị phần tử (id, name, label, placeholder, text, xpath) để lúc chạy
thử lần lượt - bền hơn số thứ tự phần tử vì số thứ tự thay đổi mỗi lần trang render.

Chạy blocking (sync Playwright) -> gọi từ QThread.
"""
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright

from services.field_locators import TEST_BROWSER_PROFILE

PICKER_JS = r"""
(() => {
  if (window.top !== window || window.__kdpmInit) return;
  window.__kdpmInit = true;
  let active = true;

  const CONTROL = 'input,textarea,select,button,a,[role=button],[contenteditable=true]';
  const normalize = (el) => {
    if (el.tagName === 'LABEL' && el.control) return el.control;
    return el.closest(CONTROL) || el;
  };
  const q = (v) => JSON.stringify(v);  // chuỗi CSS có escape

  const xpathOf = (el) => {
    const parts = [];
    for (; el && el.nodeType === 1; el = el.parentNode) {
      let i = 1;
      for (let s = el.previousElementSibling; s; s = s.previousElementSibling) if (s.tagName === el.tagName) i++;
      parts.unshift(el.tagName.toLowerCase() + '[' + i + ']');
    }
    return '/' + parts.join('/');
  };

  const describe = (raw) => {
    const el = normalize(raw);
    const tag = el.tagName.toLowerCase();
    const attr = (n) => el.getAttribute(n);
    const label = el.labels && el.labels[0] ? el.labels[0].innerText.trim() : '';
    const text = (el.innerText || el.value || '').trim();
    const c = [];
    if (attr('data-testid')) c.push({by: 'css', value: `[data-testid=${q(attr('data-testid'))}]`});
    if (el.id && !/\d{3,}/.test(el.id)) c.push({by: 'css', value: '#' + CSS.escape(el.id)});
    if (attr('name')) c.push({by: 'css', value: `${tag}[name=${q(attr('name'))}]`});
    if (label) c.push({by: 'label', value: label});
    if (attr('placeholder')) c.push({by: 'placeholder', value: attr('placeholder')});
    if (attr('aria-label')) c.push({by: 'css', value: `${tag}[aria-label=${q(attr('aria-label'))}]`});
    const isButton = tag === 'button' || tag === 'a' || attr('role') === 'button' ||
      (tag === 'input' && ['submit', 'button'].includes(el.type));
    if (isButton && text && text.length < 60) c.push({by: 'text', value: text});
    c.push({by: 'xpath', value: xpathOf(el)});
    const name = label || attr('placeholder') || attr('name') || text || '';
    return {desc: `<${tag}> ${name.slice(0, 40)}`, tag, type: el.type || '', candidates: c};
  };

  const setup = () => {
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed;pointer-events:none;border:2px solid #e53935;background:rgba(229,57,53,.12);z-index:2147483646;display:none';
    const banner = document.createElement('div');
    banner.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:8px 12px;font:14px sans-serif;color:#fff;background:#d32f2f;z-index:2147483647;text-align:center';
    document.body.append(box, banner);

    const refresh = async () => {
      const st = await window.__kdpmState();
      if (!st) { active = false; box.style.display = 'none'; banner.style.background = '#2e7d32'; banner.textContent = 'Đã chọn xong - đang lưu...'; return; }
      banner.textContent = `[${st.index}/${st.total}] Click để chọn: ${st.label}   •   F2: tạm tắt/bật chế độ chọn (để đăng nhập, mở popup...)   •   Esc: bỏ qua`;
      banner.style.background = active ? '#d32f2f' : '#616161';
    };

    document.addEventListener('mousemove', (e) => {
      if (!active || banner.contains(e.target)) { box.style.display = 'none'; return; }
      const r = normalize(e.target).getBoundingClientRect();
      Object.assign(box.style, {display: 'block', left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px'});
    }, true);

    const block = (e) => { if (active && !banner.contains(e.target)) { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); } };
    ['mousedown', 'mouseup', 'pointerdown', 'pointerup'].forEach((t) => document.addEventListener(t, block, true));
    document.addEventListener('click', async (e) => {
      if (!active || banner.contains(e.target)) return;
      block(e);
      await window.__kdpmPick(describe(e.target));
      refresh();
    }, true);

    document.addEventListener('keydown', async (e) => {
      if (e.key === 'F2') { e.preventDefault(); active = !active; if (!active) box.style.display = 'none'; refresh(); }
      else if (e.key === 'Escape' && active) { e.preventDefault(); await window.__kdpmPick(null); refresh(); }
    }, true);
    refresh();
  };

  if (document.body) setup(); else document.addEventListener('DOMContentLoaded', setup);
})();
"""


def pick_elements(url: str, labels: List[str]) -> List[Optional[Dict]]:
    """Cho người dùng chọn lần lượt phần tử ứng với `labels`. Trả về list cùng độ dài (None = bỏ qua)."""
    results: List[Optional[Dict]] = []

    def state(_source):
        i = len(results)
        if i >= len(labels):
            return None
        return {"index": i + 1, "total": len(labels), "label": labels[i]}

    def pick(_source, data):
        if len(results) < len(labels):
            results.append(data)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            TEST_BROWSER_PROFILE, headless=False, no_viewport=True, args=["--start-maximized"]
        )
        context.expose_binding("__kdpmState", state)
        context.expose_binding("__kdpmPick", pick)
        context.add_init_script(PICKER_JS)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url)

        # wait_for_timeout cũng là lúc Playwright xử lý callback từ trang
        while len(results) < len(labels):
            open_pages = [pg for pg in context.pages if not pg.is_closed()]
            if not open_pages:  # người dùng đóng trình duyệt giữa chừng
                break
            try:
                open_pages[0].wait_for_timeout(300)
            except Exception:
                break
        try:
            context.close()
        except Exception:
            pass

    return results + [None] * (len(labels) - len(results))
