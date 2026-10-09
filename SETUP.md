# Hướng dẫn setup & chạy KiemDinhPhanMem (server + app)

Thư mục gồm 2 repo:

| Repo | Vai trò | Công nghệ |
|---|---|---|
| `KiemDinhPhanMem_server/` | API, sinh testcase bằng LLM, AI agent, chấm OK/NG | FastAPI, MongoDB, Redis + Celery, ChatGPT Web (Playwright) |
| `KiemDinhPhanMem_app/` | App desktop: quản lý project/task/testcase, chạy test trên trình duyệt | PySide6, Playwright |

```
 App desktop (PySide6) ──HTTP/WS :8765──▶ Server (FastAPI) ──▶ MongoDB :27018
   │  trình duyệt test (Playwright)          │     └──▶ Celery worker ──▶ Redis :6389
   │                                          │                 │
   └─ chọn field / chạy test nhanh            └──HTTP :8800──▶ ChatGPT Web gateway ──▶ chatgpt.com
                                                                (Chrome đã đăng nhập ChatGPT)
```

LLM mặc định là **ChatGPT bản web** qua gateway (`LLM_BACKEND=chatgpt_web`), không cần OpenAI API key.
Muốn quay lại API thì đặt `LLM_BACKEND=openai` và điền `OPENAI_API_KEY` trong `.env` của server.

---

## 1. Chuẩn bị

- **Miniconda/Anaconda** (`conda --version`)
- **Docker** (Docker Desktop hoặc Rancher Desktop) để chạy MongoDB + Redis
- **Tài khoản ChatGPT** (đăng nhập 1 lần trên trình duyệt của gateway)

Không cần tài khoản nào khác: app **không có màn hình đăng nhập**, tự đăng nhập server local bằng tài khoản demo
(`DEMO_USERNAME` / `DEMO_PASSWORD`, chưa có thì tự đăng ký). Toàn bộ chạy trên máy, không kết nối hệ thống bên ngoài nào ngoài chatgpt.com.

## 2. Tạo conda env (1 lần)

Chạy tại thư mục gốc `KiemDinhPhenMem/`:

```bash
# Server - Python 3.11
conda create -y -n kdpm_server python=3.11
conda run -n kdpm_server pip install -r KiemDinhPhanMem_server/requirements.txt
conda run -n kdpm_server python -m playwright install chromium

# App - Python 3.13
conda create -y -n kdpm_app python=3.13
conda run -n kdpm_app pip install -r KiemDinhPhanMem_app/requirements.txt
conda run -n kdpm_app python -m playwright install chromium
```

---

## 3. Server

Mọi lệnh trong phần này chạy tại `KiemDinhPhanMem_server/` với `conda activate kdpm_server`.

### 3.1. File `.env`

```bash
cp .env.example .env
```

Khi chạy server **trực tiếp trên máy** (không qua docker), sửa 2 dòng sau để trỏ vào port docker map ra ngoài:

```ini
MONGO_URI="mongodb://localhost:27018/cwagentdb"
REDIS_URL="redis://localhost:6389/0"
```

Các biến LLM quan trọng:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `LLM_BACKEND` | `chatgpt_web` | `chatgpt_web` hoặc `openai` |
| `CHATGPT_WEB_URL` | `http://localhost:8800` | Địa chỉ gateway (trong docker: `http://host.docker.internal:8800`) |
| `CHATGPT_WEB_WORKERS` | `2` | Số tab ChatGPT xử lý song song |
| `CHATGPT_WEB_MODEL` | (trống) | Model của ChatGPT web, trống = model mặc định của tài khoản |
| `CHATGPT_WEB_HEADLESS` | `false` | Ẩn trình duyệt gateway (nên để `false` để xử lý Cloudflare khi cần) |
| `MAX_TESTCASE_GEN_ATTEMPTS` | `3` | Số lần sinh lại testcase tối đa khi validator báo chưa đạt |

### 3.2. MongoDB + Redis

```bash
docker compose up -d mongodb redis
```

### 3.3. Đăng nhập ChatGPT (1 lần, hoặc khi session hết hạn)

```bash
python -m chatgpt_web.login
```

Trình duyệt mở chatgpt.com → đăng nhập → quay lại terminal nhấn **Enter**.
Session lưu ở `chatgpt_web/.chatgpt_profile/` (đã gitignore). Tắt gateway trước khi chạy lệnh này.

### 3.4. Chạy (3 terminal, đều `conda activate kdpm_server`)

```bash
# Terminal 1 - ChatGPT Web gateway (để cửa sổ Chrome mở, không đóng)
python -m chatgpt_web.gateway

# Terminal 2 - API server (http://localhost:8765, docs: http://localhost:8765/docs)
python main.py

# Terminal 3 - Celery worker (sinh testcase chạy nền). Trên Windows bắt buộc --pool=solo
celery -A celery_config.celery_app worker --pool=solo --loglevel=info --queues=testcase_generation,maintenance
```

Kiểm tra gateway: mở `http://localhost:8800/health` → `{"status": "ok", ...}`.

> **Chạy server bằng docker thay vì trực tiếp:** `docker compose up -d --build` (chạy cả server, celery, mongo, redis).
> Gateway vẫn phải chạy trên máy host (bước 3.3 + Terminal 1) vì cần Chrome có giao diện; container gọi tới qua `host.docker.internal:8800`.

---

## 4. App

Mọi lệnh trong phần này chạy tại `KiemDinhPhanMem_app/` với `conda activate kdpm_app`.

### 4.1. File `.env`

```bash
cp .env.example .env
```

```ini
API_ENDPOINT=http://localhost:8765
WS_ENDPOINT=ws://localhost:8765
DEMO_USERNAME=demo
DEMO_PASSWORD=demo123456
```

### 4.2. Sinh file giao diện (1 lần, và mỗi khi sửa file `.ui`)

```bash
python tools/genui.py
```

Sinh `src/ui/build/*.py` và `src/resources_rc.py` từ `src/theme/design/*.ui`.

### 4.3. Chạy app

```bash
python src/main.py
```

App mở thẳng màn hình chính (tự đăng nhập tài khoản demo). **Server phải chạy trước**, nếu không app báo
"Không kết nối được server" rồi thoát.

---

## 5. Kịch bản demo

### 5.1. Trang web mẫu để test

```bash
# tại KiemDinhPhanMem_app/
python -m http.server 8000 -d tools/demo_site
```

Trang: `http://localhost:8000/register.html` (form Username / Email / Password có validate và toast "Đăng ký thành công!").

### 5.2. Các bước trên app

1. Tạo **Project** và **Page Viewpoint** (các ý cần test, vd: "Không nhập, nhập ký tự đặc biệt `<>&`, nhập quá 20 ký tự").
2. Tạo **Task**: URL = `http://localhost:8000/register.html`, chọn viewpoint.
3. Thêm **Specifications**: `Username` (required, 3-20), `Email` (required), `Password` (required, min 6) → **Save Specifications**.
4. Bấm **🎯 Chọn field** ở dòng task:
   - Trình duyệt mở trang, thanh đỏ trên cùng ghi field cần chọn: `[1/4] Click để chọn: 1. Username`.
   - Click lần lượt từng field, cuối cùng là nút **Đăng ký** (Submit).
   - **F2**: tạm tắt chế độ chọn (để đăng nhập / mở popup), nhấn lại để chọn tiếp. **Esc**: bỏ qua field hiện tại.
   - Xong sẽ hiện bảng tóm tắt field ↔ phần tử đã chọn.
5. Bấm **Generate testcase** → chờ Celery + ChatGPT sinh testcase.
6. Sang trang **Testcases**, chọn testcase → **▶ Run Selected**.
   - Task **đã chọn field**: app tự điền giá trị, bấm Submit, lấy message lỗi/toast + ảnh chụp, gọi `/api/judge` **1 lần** để chấm OK/NG.
   - Task **chưa chọn field**: chạy AI agent như cũ (LLM tự đọc DOM từng bước, chậm hơn nhiều).

> Web cần đăng nhập: lúc **Chọn field** nhấn F2 rồi đăng nhập luôn trong cửa sổ đó. Trình duyệt test dùng profile cố định
> (`KiemDinhPhanMem_app/.test_browser_profile/`) nên lúc chạy test vẫn giữ phiên đăng nhập.

---

## 6. File / thư mục sinh ra khi chạy (đều đã gitignore)

| Đường dẫn | Nội dung |
|---|---|
| `KiemDinhPhanMem_server/.env`, `KiemDinhPhanMem_app/.env` | Cấu hình local |
| `KiemDinhPhanMem_server/chatgpt_web/.chatgpt_profile/` | Session đăng nhập ChatGPT |
| `KiemDinhPhanMem_app/field_locators.json` | Field đã chọn theo từng task (chỉ lưu trên máy này) |
| `KiemDinhPhanMem_app/.test_browser_profile/` | Profile trình duyệt test (cookie web cần test) |
| `KiemDinhPhanMem_app/agent_local_storage.db` | Dữ liệu local của app (SQLite, đồng bộ với server) |

## 7. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `ChatGPT Web gateway 401: ... chưa đăng nhập` | Tắt gateway → `python -m chatgpt_web.login` → chạy lại gateway |
| Gateway treo ở "Just a moment..." (Cloudflare) | Nhìn cửa sổ Chrome của gateway, tick xác minh thủ công; giữ `CHATGPT_WEB_HEADLESS=false` |
| `ChatGPT Web gateway 429` | ChatGPT báo rate limit → chờ một lúc, hoặc giảm `CHATGPT_WEB_WORKERS` |
| Server báo lỗi kết nối Mongo/Redis | `docker compose up -d mongodb redis`, kiểm tra `MONGO_URI` / `REDIS_URL` dùng port 27018 / 6389 |
| Celery nhận task nhưng không chạy trên Windows | Thêm `--pool=solo` |
| App: `No module named 'ui'` | Chạy `python tools/genui.py` |
| App báo "Không kết nối được server" | Chạy server (`python main.py`) + `docker compose up -d mongodb redis`, kiểm tra `API_ENDPOINT` |
| Run báo "Không tìm thấy field ... hãy chọn lại field" | Giao diện web đã đổi → bấm **🎯 Chọn field** chọn lại |
| Lỗi `Executable doesn't exist` của Playwright | `python -m playwright install chromium` trong env tương ứng |
