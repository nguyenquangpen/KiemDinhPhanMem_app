"""
Nạp dữ liệu demo đầy đủ vào app (SQLite cục bộ) để mở app lên là có sẵn dữ liệu ở mọi trang:
project, page viewpoint, component viewpoint, template, task + field, testcase, field đã chọn,
kết quả chạy + lịch sử + ảnh minh chứng.

Các testcase của những task có trang mẫu (tools/demo_site/*.html) được CHẠY THẬT trên trình duyệt
(Playwright, dùng chính resolve/fill_value của runner nhanh trong app); kết quả OK/NG chấm bằng so khớp
thông báo trên trang với kết quả kỳ vọng (không gọi LLM, nên không cần server).

Chạy (thư mục KiemDinhPhanMem_app, env kdpm_app):
    python tools/seed_demo_data.py            # nạp dữ liệu + chạy testcase thật
    python tools/seed_demo_data.py --no-run   # chỉ nạp dữ liệu, testcase ở trạng thái chưa chạy

DB cũ (agent_local_storage.db) được đổi tên thành .bak-<thời gian> trước khi nạp.
"""
import argparse
import asyncio
import base64
import datetime as dt
import functools
import http.server
import json
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
import uuid

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(APP_ROOT, "src"))

from models.database import DataManager  # noqa: E402  (tạo đúng schema SQLite của app)
from services.field_locators import save_task_locators  # noqa: E402

DB_PATH = os.path.join(APP_ROOT, "agent_local_storage.db")
SCREENSHOT_DIR = os.path.join(APP_ROOT, "screenshots")
DEMO_SITE = os.path.join(APP_ROOT, "tools", "demo_site")
SITE_PORT = 8000
SITE = f"http://localhost:{SITE_PORT}"
USERNAME = os.getenv("DEMO_USERNAME", "demo")


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ----------------------------------------------------------------------------- viewpoint
def detail(desc, err, result):
    return {"detail_id": new_id(), "description_input": desc, "error_message_expected": err, "final_result_expected": result}


COMPONENT_VPS = {
    "Field bắt buộc": [
        detail("Bỏ trống field", "<Field> là bắt buộc", "Không submit được"),
        detail("Chỉ nhập khoảng trắng", "<Field> là bắt buộc / không hợp lệ", "Không submit được"),
    ],
    "Độ dài min - max": [
        detail("Nhập min-1 ký tự", "Độ dài không hợp lệ", "Không submit được"),
        detail("Nhập đúng min ký tự", "", "Submit thành công"),
        detail("Nhập đúng max ký tự", "", "Submit thành công"),
        detail("Nhập max+1 ký tự", "Độ dài không hợp lệ", "Không submit được"),
    ],
    "Ký tự đặc biệt": [
        detail("Nhập từng ký tự đặc biệt < > & ' (mỗi ký tự 1 testcase)", "Chỉ cho phép chữ và số", "Không submit được"),
    ],
    "Định dạng email": [
        detail("Email thiếu @", "Email không đúng định dạng", "Không submit được"),
        detail("Email thiếu tên miền", "Email không đúng định dạng", "Không submit được"),
        detail("Email chứa khoảng trắng", "Email không đúng định dạng", "Không submit được"),
    ],
    "Chỉ nhập chữ số": [
        detail("Nhập chuỗi có chữ cái", "Chỉ được nhập chữ số", "Không submit được"),
        detail("Nhập thiếu 1 chữ số", "Độ dài không hợp lệ", "Không submit được"),
        detail("Nhập thừa 1 chữ số", "Độ dài không hợp lệ", "Không submit được"),
    ],
    "Định dạng ngày MM/YY": [
        detail("Tháng không hợp lệ (13)", "Sai định dạng MM/YY", "Không submit được"),
        detail("Ngày đã hết hạn", "Thẻ đã hết hạn", "Không submit được"),
    ],
    "Chọn giá trị trong danh sách": [
        detail("Không chọn giá trị nào", "Vui lòng chọn", "Không submit được"),
    ],
}
PAGE_VPS = {
    "Đăng ký tài khoản": [
        detail("Nhập đầy đủ dữ liệu hợp lệ và bấm Đăng ký", "", "Hiển thị: Đăng ký thành công"),
        detail("Bỏ trống tất cả các field và bấm Đăng ký", "Lỗi bắt buộc dưới từng field", "Không đăng ký được"),
    ],
    "Đăng nhập": [
        detail("Đăng nhập đúng tài khoản", "", "Hiển thị: Đăng nhập thành công"),
        detail("Sai mật khẩu / tài khoản không tồn tại", "Sai tên đăng nhập hoặc mật khẩu", "Ở lại trang đăng nhập"),
        detail("Username có khoảng trắng đầu/cuối", "", "Hệ thống tự cắt khoảng trắng, đăng nhập thành công"),
    ],
    "Thêm mới bản ghi": [
        detail("Nhập dữ liệu hợp lệ và bấm Lưu", "", "Hiển thị: Thêm thành công"),
        detail("Thiếu field bắt buộc", "Lỗi bắt buộc", "Không lưu được"),
    ],
    "Thanh toán": [
        detail("Nhập thông tin thẻ hợp lệ", "", "Hiển thị: Thanh toán thành công"),
        detail("Thông tin thẻ không hợp lệ", "Lỗi dưới field sai", "Không thanh toán được"),
    ],
}


# ----------------------------------------------------------------------------- dữ liệu project / task / testcase
def item(name, required, mn, mx, spec, default, vps):
    return {"item_name": name, "required": required, "min": mn, "max": mx, "spec": spec, "default": default, "validation_types": vps}


def tc(field, ttype, case, ref, expect):
    return {"test_field": field, "test_type": ttype, "test_case": case, "test_reference": ref, "test_expect": expect}


REG_OK = {"Username": "tester01", "Email": "tester01@example.com", "Password": "Test@1234"}
LOGIN_OK = {"Username": "tester01", "Password": "Test@1234"}
USER_OK = {"Họ tên": "Nguyễn Văn An", "Email": "an.nguyen@company.com", "Số điện thoại": "0912345678", "Vai trò": "Staff"}
CARD_OK = {"Số thẻ": "4111111111111111", "Tên chủ thẻ": "NGUYEN VAN AN", "Ngày hết hạn": "12/28", "CVV": "123"}

ERR_REG = "Hiển thị lỗi dưới field, không đăng ký được"
OK_REG = "Hiển thị: Đăng ký thành công"


def register_cases():
    cases = [
        tc("Đăng ký tài khoản", "Hợp lệ", "Nhập đầy đủ dữ liệu hợp lệ và bấm Đăng ký", REG_OK, OK_REG),
        tc("Đăng ký tài khoản", "Bỏ trống", "Bỏ trống tất cả các field", {"Username": "", "Email": "", "Password": ""}, "Hiển thị lỗi bắt buộc dưới từng field"),
        tc("Field bắt buộc (Username)", "Bỏ trống", "Bỏ trống Username", {**REG_OK, "Username": ""}, "Hiển thị: Username là bắt buộc"),
        tc("Field bắt buộc (Username)", "Khoảng trắng", "Username chỉ gồm khoảng trắng", {**REG_OK, "Username": "   "}, ERR_REG),
        tc("Độ dài min - max (Username)", "Biên dưới", "Username 2 ký tự (min-1)", {**REG_OK, "Username": "ab"}, "Hiển thị lỗi độ dài 3-20 ký tự"),
        tc("Độ dài min - max (Username)", "Biên dưới", "Username 3 ký tự (min)", {**REG_OK, "Username": "abc"}, OK_REG),
        tc("Độ dài min - max (Username)", "Biên trên", "Username 20 ký tự (max)", {**REG_OK, "Username": "a" * 20}, OK_REG),
        tc("Độ dài min - max (Username)", "Biên trên", "Username 21 ký tự (max+1)", {**REG_OK, "Username": "a" * 21}, "Hiển thị lỗi độ dài 3-20 ký tự"),
    ]
    for ch in ["<", ">", "&", "'"]:
        cases.append(tc("Ký tự đặc biệt (Username)", "Ký tự đặc biệt", f"Username chứa ký tự {ch}", {**REG_OK, "Username": f"abc{ch}"}, "Hiển thị: chỉ gồm chữ và số"))
    cases += [
        tc("Field bắt buộc (Email)", "Bỏ trống", "Bỏ trống Email", {**REG_OK, "Email": ""}, "Hiển thị: Email là bắt buộc"),
        tc("Định dạng email (Email)", "Sai định dạng", "Email thiếu @", {**REG_OK, "Email": "tester01example.com"}, "Hiển thị: Email không đúng định dạng"),
        tc("Định dạng email (Email)", "Sai định dạng", "Email thiếu tên miền", {**REG_OK, "Email": "tester01@"}, "Hiển thị: Email không đúng định dạng"),
        tc("Định dạng email (Email)", "Sai định dạng", "Email chứa khoảng trắng", {**REG_OK, "Email": "tester 01@example.com"}, "Hiển thị: Email không đúng định dạng"),
        tc("Field bắt buộc (Password)", "Bỏ trống", "Bỏ trống Password", {**REG_OK, "Password": ""}, "Hiển thị: Password là bắt buộc"),
        tc("Độ dài min - max (Password)", "Biên dưới", "Password 5 ký tự (min-1)", {**REG_OK, "Password": "12345"}, "Hiển thị: Password tối thiểu 6 ký tự"),
        tc("Độ dài min - max (Password)", "Biên dưới", "Password 6 ký tự (min)", {**REG_OK, "Password": "123456"}, OK_REG),
        tc("Độ dài min - max (Password)", "Biên trên", "Password 32 ký tự (max)", {**REG_OK, "Password": "P" * 32}, OK_REG),
        tc("Độ dài min - max (Password)", "Biên trên", "Password 33 ký tự (max+1)", {**REG_OK, "Password": "P" * 33}, "Hiển thị lỗi: Password tối đa 32 ký tự"),
    ]
    return cases


def login_cases():
    return [
        tc("Đăng nhập", "Hợp lệ", "Đăng nhập đúng tài khoản tester01", LOGIN_OK, "Hiển thị: Đăng nhập thành công"),
        tc("Đăng nhập", "Sai thông tin", "Sai mật khẩu", {**LOGIN_OK, "Password": "Wrong@123"}, "Hiển thị: Sai tên đăng nhập hoặc mật khẩu"),
        tc("Đăng nhập", "Sai thông tin", "Tài khoản không tồn tại", {**LOGIN_OK, "Username": "khongtontai"}, "Hiển thị: Sai tên đăng nhập hoặc mật khẩu"),
        tc("Đăng nhập", "Sai thông tin", "Mật khẩu sai hoa/thường (test@1234)", {**LOGIN_OK, "Password": "test@1234"}, "Hiển thị: Sai tên đăng nhập hoặc mật khẩu"),
        tc("Đăng nhập", "Khoảng trắng", "Username có khoảng trắng đầu/cuối", {**LOGIN_OK, "Username": " tester01 "}, "Tự cắt khoảng trắng, hiển thị: Đăng nhập thành công"),
        tc("Field bắt buộc (Username)", "Bỏ trống", "Bỏ trống Username", {**LOGIN_OK, "Username": ""}, "Hiển thị: Username là bắt buộc"),
        tc("Field bắt buộc (Password)", "Bỏ trống", "Bỏ trống Password", {**LOGIN_OK, "Password": ""}, "Hiển thị: Password là bắt buộc"),
        tc("Đăng nhập", "Bỏ trống", "Bỏ trống cả Username và Password", {"Username": "", "Password": ""}, "Hiển thị lỗi bắt buộc dưới 2 field"),
    ]


def add_user_cases():
    return [
        tc("Thêm mới bản ghi", "Hợp lệ", "Nhập dữ liệu hợp lệ và bấm Lưu", USER_OK, "Hiển thị: Thêm người dùng thành công"),
        tc("Thêm mới bản ghi", "Hợp lệ", "Họ tên tiếng Việt có dấu, vai trò Admin", {**USER_OK, "Họ tên": "Trần Thị Bích Ngọc", "Vai trò": "Admin"}, "Hiển thị: Thêm người dùng thành công"),
        tc("Field bắt buộc (Họ tên)", "Bỏ trống", "Bỏ trống Họ tên", {**USER_OK, "Họ tên": ""}, "Hiển thị: Họ tên là bắt buộc"),
        tc("Độ dài min - max (Họ tên)", "Biên dưới", "Họ tên 1 ký tự (min-1)", {**USER_OK, "Họ tên": "A"}, "Hiển thị lỗi độ dài 2-50 ký tự"),
        tc("Độ dài min - max (Họ tên)", "Biên trên", "Họ tên 51 ký tự (max+1)", {**USER_OK, "Họ tên": "A" * 51}, "Hiển thị lỗi độ dài 2-50 ký tự"),
        tc("Định dạng email (Email)", "Sai định dạng", "Email thiếu @", {**USER_OK, "Email": "an.nguyen.company.com"}, "Hiển thị: Email không đúng định dạng"),
        tc("Chỉ nhập chữ số (Số điện thoại)", "Thiếu số", "Số điện thoại 9 chữ số", {**USER_OK, "Số điện thoại": "091234567"}, "Hiển thị: Số điện thoại phải có 10 số"),
        tc("Chỉ nhập chữ số (Số điện thoại)", "Thừa số", "Số điện thoại 11 chữ số", {**USER_OK, "Số điện thoại": "09123456789"}, "Hiển thị: Số điện thoại phải có 10 số"),
        tc("Chỉ nhập chữ số (Số điện thoại)", "Có chữ cái", "Số điện thoại chứa chữ cái (09abc12345)", {**USER_OK, "Số điện thoại": "09abc12345"}, "Hiển thị lỗi: chỉ được nhập chữ số"),
        tc("Chọn giá trị trong danh sách (Vai trò)", "Không chọn", "Không chọn vai trò", {**USER_OK, "Vai trò": ""}, "Hiển thị: Vui lòng chọn vai trò"),
    ]


def search_user_cases():
    return [
        tc("Tìm kiếm", "Hợp lệ", "Tìm theo họ tên chính xác", {"Từ khoá": "Nguyễn Văn An"}, "Hiển thị đúng 1 kết quả"),
        tc("Tìm kiếm", "Không dấu", "Tìm theo họ tên không dấu", {"Từ khoá": "nguyen van an"}, "Vẫn tìm thấy người dùng"),
        tc("Tìm kiếm", "Không có kết quả", "Từ khoá không tồn tại", {"Từ khoá": "zzzz"}, "Hiển thị: Không tìm thấy kết quả"),
        tc("Ký tự đặc biệt (Từ khoá)", "Ký tự đặc biệt", "Từ khoá chứa ký tự %", {"Từ khoá": "%"}, "Không lỗi hệ thống, hiển thị không có kết quả"),
    ]


def checkout_cases():
    return [
        tc("Thanh toán", "Hợp lệ", "Nhập thông tin thẻ hợp lệ", CARD_OK, "Hiển thị: Thanh toán thành công"),
        tc("Chỉ nhập chữ số (Số thẻ)", "Thiếu số", "Số thẻ 15 chữ số", {**CARD_OK, "Số thẻ": "411111111111111"}, "Hiển thị: Số thẻ phải gồm 16 chữ số"),
        tc("Chỉ nhập chữ số (Số thẻ)", "Thừa số", "Số thẻ 17 chữ số", {**CARD_OK, "Số thẻ": "41111111111111111"}, "Hiển thị: Số thẻ phải gồm 16 chữ số"),
        tc("Chỉ nhập chữ số (Số thẻ)", "Có chữ cái", "Số thẻ chứa chữ cái", {**CARD_OK, "Số thẻ": "4111abcd11111111"}, "Hiển thị: Số thẻ phải gồm 16 chữ số"),
        tc("Field bắt buộc (Tên chủ thẻ)", "Bỏ trống", "Bỏ trống Tên chủ thẻ", {**CARD_OK, "Tên chủ thẻ": ""}, "Hiển thị: Tên chủ thẻ là bắt buộc"),
        tc("Định dạng ngày MM/YY (Ngày hết hạn)", "Sai định dạng", "Tháng 13 (13/27)", {**CARD_OK, "Ngày hết hạn": "13/27"}, "Hiển thị: Ngày hết hạn phải có dạng MM/YY"),
        tc("Định dạng ngày MM/YY (Ngày hết hạn)", "Hết hạn", "Thẻ đã hết hạn (01/20)", {**CARD_OK, "Ngày hết hạn": "01/20"}, "Hiển thị: Thẻ đã hết hạn"),
        tc("Chỉ nhập chữ số (CVV)", "Thiếu số", "CVV 2 chữ số", {**CARD_OK, "CVV": "12"}, "Hiển thị: CVV phải gồm 3 chữ số"),
        tc("Chỉ nhập chữ số (CVV)", "Thừa số", "CVV 4 chữ số", {**CARD_OK, "CVV": "1234"}, "Hiển thị: CVV phải gồm 3 chữ số"),
        tc("Chỉ nhập chữ số (CVV)", "Có chữ cái", "CVV chứa chữ cái", {**CARD_OK, "CVV": "12a"}, "Hiển thị: CVV phải gồm 3 chữ số"),
    ]


def loc(css, label, tag="input", type_=""):
    return {"desc": f"<{tag}> {label}", "tag": tag, "type": type_,
            "candidates": [{"by": "css", "value": css}, {"by": "label", "value": label}]}


def submit(text):
    return {"desc": f"<button> {text}", "tag": "button", "type": "submit",
            "candidates": [{"by": "text", "value": text}, {"by": "css", "value": "button[type=submit]"}]}


# Mỗi project: (tên, url, mô tả, login_id, password, page viewpoints, component viewpoints, tasks)
# Mỗi task: (tên, url, page viewpoint, items(fn nhận dict vp), testcases, locators | None)
PROJECTS = [
    ("Website Đăng ký thành viên", f"{SITE}/register.html", "Kiểm thử chức năng đăng ký và đăng nhập tài khoản thành viên", "tester01", "Test@1234",
     ["Đăng ký tài khoản", "Đăng nhập"], ["Field bắt buộc", "Độ dài min - max", "Ký tự đặc biệt", "Định dạng email"],
     [("Form đăng ký tài khoản", f"{SITE}/register.html", "Đăng ký tài khoản",
       lambda v: [item("Username", True, 3, 20, "Chỉ gồm chữ và số", "tester01", [v["Field bắt buộc"], v["Độ dài min - max"], v["Ký tự đặc biệt"]]),
                  item("Email", True, 6, 100, "Đúng định dạng email", "tester01@example.com", [v["Field bắt buộc"], v["Định dạng email"]]),
                  item("Password", True, 6, 32, "Tối thiểu 6, tối đa 32 ký tự", "Test@1234", [v["Field bắt buộc"], v["Độ dài min - max"]])],
       register_cases(),
       {"fields": {"Username": loc("#username", "Username"), "Email": loc("#email", "Email"),
                   "Password": loc("#password", "Password", type_="password")}, "submit": submit("Đăng ký")}),
      ("Form đăng nhập", f"{SITE}/login.html", "Đăng nhập",
       lambda v: [item("Username", True, 3, 20, "Tự cắt khoảng trắng đầu/cuối", "tester01", [v["Field bắt buộc"]]),
                  item("Password", True, 6, 32, "Phân biệt hoa thường", "Test@1234", [v["Field bắt buộc"]])],
       login_cases(),
       {"fields": {"Username": loc("#username", "Username"), "Password": loc("#password", "Password", type_="password")},
        "submit": submit("Đăng nhập")})]),
    ("Trang quản trị nội bộ", f"{SITE}/add_user.html", "Kiểm thử màn hình quản lý người dùng của trang quản trị", "admin", "Admin@123",
     ["Thêm mới bản ghi"], ["Field bắt buộc", "Độ dài min - max", "Định dạng email", "Chỉ nhập chữ số", "Chọn giá trị trong danh sách"],
     [("Thêm người dùng", f"{SITE}/add_user.html", "Thêm mới bản ghi",
       lambda v: [item("Họ tên", True, 2, 50, "Cho phép tiếng Việt có dấu", "Nguyễn Văn An", [v["Field bắt buộc"], v["Độ dài min - max"]]),
                  item("Email", True, 6, 100, "Đúng định dạng email", "an.nguyen@company.com", [v["Field bắt buộc"], v["Định dạng email"]]),
                  item("Số điện thoại", True, 10, 10, "Đúng 10 chữ số", "0912345678", [v["Chỉ nhập chữ số"]]),
                  item("Vai trò", True, 0, 0, "Admin / Staff / User", "Staff", [v["Chọn giá trị trong danh sách"]])],
       add_user_cases(),
       {"fields": {"Họ tên": loc("#fullname", "Họ tên"), "Email": loc("#email", "Email"),
                   "Số điện thoại": loc("#phone", "Số điện thoại"), "Vai trò": loc("#role", "Vai trò", tag="select")},
        "submit": submit("Lưu")}),
      ("Tìm kiếm người dùng", f"{SITE}/users.html", "Thêm mới bản ghi",
       lambda v: [item("Từ khoá", False, 0, 100, "Tìm theo họ tên, không phân biệt dấu", "", [v["Độ dài min - max"]])],
       search_user_cases(), None)]),
    ("Cổng thanh toán", f"{SITE}/checkout.html", "Kiểm thử form nhập thông tin thẻ thanh toán", "", "",
     ["Thanh toán"], ["Field bắt buộc", "Chỉ nhập chữ số", "Định dạng ngày MM/YY"],
     [("Nhập thông tin thẻ", f"{SITE}/checkout.html", "Thanh toán",
       lambda v: [item("Số thẻ", True, 16, 16, "Đúng 16 chữ số", "4111111111111111", [v["Field bắt buộc"], v["Chỉ nhập chữ số"]]),
                  item("Tên chủ thẻ", True, 2, 50, "Chữ in hoa không dấu", "NGUYEN VAN AN", [v["Field bắt buộc"]]),
                  item("Ngày hết hạn", True, 5, 5, "Dạng MM/YY, chưa hết hạn", "12/28", [v["Định dạng ngày MM/YY"]]),
                  item("CVV", True, 3, 3, "Đúng 3 chữ số", "123", [v["Chỉ nhập chữ số"]])],
       checkout_cases(),
       {"fields": {"Số thẻ": loc("#card_number", "Số thẻ"), "Tên chủ thẻ": loc("#card_holder", "Tên chủ thẻ"),
                   "Ngày hết hạn": loc("#expiry", "Ngày hết hạn"), "CVV": loc("#cvv", "CVV")}, "submit": submit("Thanh toán")})]),
]

TEMPLATES = [("component", n) for n in COMPONENT_VPS] + [("page", n) for n in PAGE_VPS]


# ----------------------------------------------------------------------------- ghi SQLite
def seed_database(base_time: dt.datetime):
    if os.path.exists(DB_PATH):
        backup = f"{DB_PATH}.bak-{dt.datetime.now():%Y%m%d_%H%M%S}"
        shutil.move(DB_PATH, backup)
        print(f"DB cũ đã đổi tên thành {os.path.basename(backup)}")

    locators_file = os.path.join(APP_ROOT, "field_locators.json")
    if os.path.exists(locators_file):
        os.remove(locators_file)  # locator cũ trỏ tới task của DB cũ
    db = DataManager(DB_PATH, None, use_api=False)  # tạo đủ bảng theo schema của app
    cur = db.cursor
    cur.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (USERNAME,))
    cur.execute("SELECT id FROM users WHERE username = ?", (USERNAME,))
    user_id = cur.fetchone()["id"]
    cur.execute("INSERT INTO sync_settings (user_id, enabled, auto_sync, interval_sync, interval_ms, updated_at) VALUES (?, 0, 0, 0, 300000, ?)",
                (user_id, iso(base_time)))

    for i, (vtype, name) in enumerate(TEMPLATES):
        details = COMPONENT_VPS.get(name) or PAGE_VPS.get(name)
        t = iso(base_time + dt.timedelta(minutes=i))
        cur.execute("INSERT INTO viewpoints_templates (uuid, name, viewpoint_type, viewpoint_details, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (new_id(), name, vtype, json.dumps(details, ensure_ascii=False), t, t))

    runnable = []  # (testcase row, task url, locators)
    for p_idx, (pname, purl, pdesc, login_id, password, page_vps, comp_vps, tasks) in enumerate(PROJECTS):
        p_time = base_time + dt.timedelta(days=p_idx, hours=1)
        project_id = new_id()
        cur.execute("""INSERT INTO projects (uuid, user_id, name, url, description, login_id, password, created_at, updated_at, created_by, testcase_generated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (project_id, user_id, pname, purl, pdesc, login_id, password, iso(p_time), iso(p_time), user_id))

        vps = {}
        for v_idx, (vtype, names) in enumerate((("page", page_vps), ("component", comp_vps))):
            for name in names:
                details = PAGE_VPS.get(name) if vtype == "page" else COMPONENT_VPS[name]
                vp = {"uuid": new_id(), "name": name, "viewpoint_type": vtype,
                      "viewpoint_details": [{**d, "detail_id": new_id()} for d in details]}
                t = iso(p_time + dt.timedelta(minutes=10 + len(vps)))
                cur.execute("""INSERT INTO viewpoints (uuid, project_id, name, viewpoint_type, details_json, created_at, updated_at, created_by)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (vp["uuid"], project_id, name, vtype, json.dumps(vp["viewpoint_details"], ensure_ascii=False), t, t, user_id))
                vps[name] = vp

        for t_idx, (tname, turl, page_vp, items_fn, cases, locators) in enumerate(tasks):
            task_id = new_id()
            t_time = p_time + dt.timedelta(hours=2 + t_idx)
            items = items_fn(vps)
            cur.execute("""INSERT INTO tasks (uuid, project_id, task_name, url_test, viewpoint_id, request_login, specs_json, created_at, updated_at,
                           created_by, generation_started_at, generation_status, include_component_viewpoints, generation_completed_at, testcases_generated, status)
                           VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 'completed', 1, ?, ?, 'completed')""",
                        (task_id, project_id, tname, turl, vps[page_vp]["uuid"], json.dumps(items, ensure_ascii=False),
                         iso(t_time), iso(t_time), user_id, iso(t_time + dt.timedelta(minutes=1)),
                         iso(t_time + dt.timedelta(minutes=4)), len(cases)))
            if locators:
                save_task_locators(task_id, locators["fields"], locators["submit"])
            for c in cases:
                row = {**c, "uuid": new_id(), "task_uuid": task_id, "project_id": project_id}
                created = iso(t_time + dt.timedelta(minutes=4))
                cur.execute("""INSERT INTO testcases (uuid, task_uuid, project_id, test_field, test_type, test_case, test_reference, test_expect,
                               test_status, created_at, updated_at, step_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'not_started', ?, ?, 0)""",
                            (row["uuid"], task_id, project_id, c["test_field"], c["test_type"], c["test_case"],
                             json.dumps(c["test_reference"], ensure_ascii=False), c["test_expect"], created, created))
                if locators:
                    runnable.append((row, turl, locators))
        print(f"Project '{pname}': {len(tasks)} task, {sum(len(t[4]) for t in tasks)} testcase")
    db.conn.commit()
    return db, runnable


# ----------------------------------------------------------------------------- chạy testcase thật trên trang mẫu
def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()[:60] or "test"


def judge(expect: str, messages):
    """OK/NG bằng so khớp: kỳ vọng thành công <-> trang hiện thông báo thành công; kỳ vọng lỗi <-> có thông báo lỗi."""
    success = [m for m in messages if "thành công" in m.lower()]
    errors = [m for m in messages if m not in success]
    if "thành công" in expect.lower() and not expect.lower().startswith("không"):
        if success:
            return True, ""
        return False, f"Kỳ vọng: {expect}. Thực tế: không có thông báo thành công" + (f" (trang báo: {'; '.join(errors)})" if errors else "")
    if errors and not success:
        return True, ""
    return False, f"Kỳ vọng: {expect}. Thực tế: không hiển thị lỗi, form vẫn submit ({'; '.join(success) or 'không có thông báo'})"


async def run_all(db, runnable):
    from playwright.async_api import async_playwright
    from services.quick_runner import _COLLECT_MESSAGES_JS, fill_value, resolve

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", SITE_PORT), functools.partial(QuietHandler, directory=DEMO_SITE))
        threading.Thread(target=server.serve_forever, daemon=True).start()
    except OSError:
        server = None  # cổng đang được dùng: coi như bạn đã tự chạy `python -m http.server 8000 -d tools/demo_site`

    stats = {"passed": 0, "failed": 0, "error": 0}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for i, (row, url, locators) in enumerate(runnable, 1):
            start = dt.datetime.now(dt.timezone.utc)
            t0 = time.perf_counter()
            page = await browser.new_page(viewport={"width": 1000, "height": 700})
            shots, status, error = [], "error", ""
            try:
                await page.goto(url.replace("localhost", "127.0.0.1"))
                for name, value in row["test_reference"].items():
                    element = await resolve(page, locators["fields"][name])
                    if element is None:
                        raise RuntimeError(f"Không tìm thấy field '{name}'")
                    await fill_value(element, locators["fields"][name], value)
                shots.append(await page.screenshot(full_page=True))
                button = await resolve(page, locators["submit"])
                await button.click()
                await page.wait_for_timeout(500)
                messages = await page.evaluate(_COLLECT_MESSAGES_JS)
                shots.append(await page.screenshot(full_page=True))
                ok, error = judge(row["test_expect"], messages)
                status = "passed" if ok else "failed"
            except Exception as e:
                error = str(e)
            finally:
                await page.close()
            end = dt.datetime.now(dt.timezone.utc)
            stats[status] += 1

            run_dir = os.path.join(SCREENSHOT_DIR, row["uuid"], end.astimezone().strftime("%Y%m%d_%H%M%S"))
            os.makedirs(run_dir, exist_ok=True)
            for n, png in enumerate(shots, 1):
                with open(os.path.join(run_dir, f"{slugify(row['test_case'])}_{n:02d}.png"), "wb") as f:
                    f.write(png)
            history = [{"status": status, "start_time": start.astimezone().isoformat(), "end_time": end.astimezone().isoformat(),
                        "error_message": error, "screenshots_count": len(shots),
                        "execution_id": f"{row['uuid']}_{end.astimezone():%Y%m%d_%H%M%S}", "duration": round(time.perf_counter() - t0, 2)}]
            db.cursor.execute("""UPDATE testcases SET test_status = ?, last_run_status = ?, last_run_time = ?, test_result_details = ?, updated_at = ?
                                 WHERE uuid = ?""",
                              ({"passed": "is_done", "failed": "is_error"}.get(status, "is_error"), status.title(),
                               end.astimezone().isoformat(), json.dumps(history, ensure_ascii=False), end.isoformat(), row["uuid"]))
            print(f"  [{i:2d}/{len(runnable)}] {status.upper():6s} {row['test_case']}" + (f"  → {error}" if status != "passed" else ""))
        await browser.close()
    if server:
        server.shutdown()
    db.conn.commit()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Nạp dữ liệu demo cho app CWTestAgent")
    parser.add_argument("--no-run", action="store_true", help="chỉ nạp dữ liệu, không chạy testcase trên trình duyệt")
    args = parser.parse_args()

    base_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=6)
    db, runnable = seed_database(base_time)
    if args.no_run:
        print("Bỏ qua bước chạy testcase (--no-run).")
    else:
        print(f"Chạy {len(runnable)} testcase trên trang mẫu…")
        stats = asyncio.run(run_all(db, runnable))
        print(f"Kết quả: {stats['passed']} OK · {stats['failed']} NG · {stats['error']} lỗi thực thi")
    db.conn.close()
    print(f"Xong. DB: {DB_PATH}\nMở app: python src/main.py")


if __name__ == "__main__":
    main()
