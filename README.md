# CWTestAgent – Ứng dụng desktop (KiemDinhPhanMem_app)

**Công cụ dùng AI hỗ trợ tester tự sinh testcase và tự chạy testcase cho ứng dụng web.**

Đề tài môn *Đánh giá và kiểm định chất lượng phần mềm* · Sinh viên thực hiện: **Nguyễn Trần Quang**

| Repo | Vai trò | Link |
|---|---|---|
| **KiemDinhPhanMem_app** (repo này) | Ứng dụng desktop tester sử dụng: khai báo, chạy test, xem kết quả | https://github.com/nguyenquangpen/KiemDinhPhanMem_app |
| **KiemDinhPhanMem_server** | Server xử lý: lưu dữ liệu, gọi AI sinh testcase, chấm OK/NG | https://github.com/nguyenquangpen/KiemDinhPhanMem_server |

Hệ thống gồm **cả hai repo**. App cần server chạy để dùng các chức năng AI.

---

## 1. Đề tài giải quyết vấn đề gì?

Chỉ một form đăng ký có 3 ô (Username, Email, Password) đã cần **30–50 testcase**. Lý do: mỗi ô phải được thử bỏ trống, giá trị biên (min−1, min, max, max+1), ký tự đặc biệt, sai định dạng… Một hệ thống vài chục màn hình sẽ có **hàng nghìn testcase**, và mỗi lần phát hành phiên bản mới lại phải chạy lại toàn bộ.

Tester đang mất nhiều thời gian ở 4 việc:

1. **Viết testcase lặp lại:** các màn hình có cách thử gần giống nhau, nhưng lần nào cũng viết lại.
2. **Chất lượng không đồng đều:** mỗi người viết một kiểu, dễ gộp nhiều ý vào một case hoặc bỏ sót.
3. **Chạy tay mỗi lần phát hành:** nhập liệu, bấm nút, chụp màn hình, ghi OK/NG thủ công.
4. **Công cụ tự động hiện có (Selenium, Playwright) vẫn bắt viết code** kịch bản, và kịch bản dễ hỏng khi giao diện thay đổi.

## 2. Giải pháp

CWTestAgent tự động hoá **hai khâu tốn công nhất: thiết kế testcase và thực thi testcase.**

```
 Tester khai báo        AI sinh testcase        Công cụ tự chạy trên       Kết quả OK/NG
 field + viewpoint  ──▶  và tự kiểm duyệt   ──▶  trình duyệt thật       ──▶  kèm ảnh minh chứng
```

Tester **không bị thay thế**: tester vẫn quyết định *cần test cái gì* và *xem lại kết quả*. Công cụ chỉ làm thay phần việc lặp đi lặp lại.

## 3. Các khái niệm chính

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Project** | Một ứng dụng web cần kiểm thử. Lưu URL và tài khoản đăng nhập (nếu web yêu cầu). | "Website ABC", `https://abc.com` |
| **Task** | Một màn hình cần test, kèm danh sách các ô nhập (field) và quy định của từng ô (spec). | "Form đăng nhập": Username bắt buộc, 3–20 ký tự |
| **Page viewpoint** | Góc nhìn kiểm thử của **cả màn hình**: các tình huống nghiệp vụ. Mỗi task chọn 1 page viewpoint. | "Đăng nhập đúng tài khoản → vào được hệ thống"; "Sai mật khẩu → báo lỗi" |
| **Component viewpoint** | Góc nhìn kiểm thử của **từng ô nhập**: quy tắc kiểm tra dùng lại được cho mọi ô ở mọi màn hình. Mỗi ô gán tối đa 5. | "Độ dài min–max": thử min−1, min, max, max+1 |
| **Template** | Viewpoint mẫu, lưu lại để dùng cho các dự án khác. | Bộ viewpoint chuẩn của đội QA |
| **Testcase** | Một lần thử cụ thể: dữ liệu nhập và kết quả kỳ vọng. Do AI sinh từ spec và viewpoint, tester sửa được. | Username = "ab" → kỳ vọng báo lỗi độ dài |
| **OK / NG** | Kết quả chạy: **OK** là trang web chạy đúng kỳ vọng; **NG** là sai kỳ vọng, tức phát hiện lỗi. | Username 21 ký tự vẫn đăng ký được → **NG** |

**Ví dụ cách AI sinh testcase.** Spec của Username là bắt buộc, dài 3–20 ký tự. Ghép với component viewpoint "Độ dài min–max", AI sinh ra:

| Dữ liệu nhập | Kết quả kỳ vọng |
|---|---|
| `ab` (2 ký tự, min−1) | Báo lỗi độ dài |
| `abc` (3 ký tự, min) | Thành công |
| 20 ký tự (max) | Thành công |
| 21 ký tự (max+1) | Báo lỗi độ dài |

Đây chính là **kỹ thuật phân tích giá trị biên**, được đóng gói sẵn trong viewpoint.

## 4. Cách sử dụng: 6 bước

| Bước | Ai làm | Việc làm |
|---|---|---|
| 1 | Tester | Tạo **Project**: nhập URL web cần test và tài khoản đăng nhập (nếu có). |
| 2 | Tester | Tạo hoặc chọn **viewpoint** (page và component), có thể lấy từ template. |
| 3 | Tester | Tạo **Task**: chọn page viewpoint, khai báo từng ô (bắt buộc, min, max, quy tắc, giá trị mẫu) và gán component viewpoint. |
| 4 | AI | **Sinh testcase**: chuẩn hoá spec → sinh testcase theo từng dòng viewpoint → AI thứ hai kiểm duyệt độ phủ, chưa đạt thì sinh lại (tối đa 3 lần). Chạy nền nên app không bị treo. |
| 5 | Tester | **Chọn field trên trang**: công cụ mở trang web, tester click lần lượt từng ô và nút Submit. Công cụ lưu nhiều cách định vị (id, name, nhãn, xpath) để bền hơn khi giao diện đổi nhẹ. |
| 6 | Công cụ | **Chạy testcase** trên trình duyệt thật, chấm OK/NG, lưu ảnh trước/sau và lịch sử chạy. |

Bước 1–3 và 5 chỉ làm **một lần cho mỗi màn hình**. Bước 6 chạy lại bao nhiêu lần cũng được (kiểm thử hồi quy).

**Hai chế độ chạy testcase:**

| Chế độ | Khi nào dùng | Cách hoạt động |
|---|---|---|
| **Runner nhanh** (mặc định) | Task đã chọn field ở bước 5 | Điền dữ liệu → bấm Submit → thu thông báo lỗi và ảnh chụp → gọi AI **1 lần** để chấm OK/NG. |
| **AI Agent** (dự phòng) | Task chưa chọn field, hoặc luồng nhiều bước | AI đọc trang (các phần tử được đánh số), chọn hành động, lặp lại từng bước như người dùng thật. Linh hoạt hơn nhưng chậm hơn. |

## 5. Kiến trúc hệ thống

```
 ┌──────── Máy tester (repo này) ───────┐          ┌──────── KiemDinhPhanMem_server ────────┐
 │ App desktop (PySide6)                │ HTTP/WS  │ API (FastAPI) – MongoDB                │
 │ Trình duyệt Chromium (Playwright)    │ ───────▶ │ Sinh testcase chạy nền (Celery+Redis)  │
 │ Dữ liệu cục bộ (SQLite)              │          │ AI Agent + chấm OK/NG                  │
 └──────────────────────────────────────┘          └──────────────────┬─────────────────────┘
                                                                      │ HTTP
                                                              ChatGPT (gateway web
                                                              hoặc OpenAI API)
```

- **Server là "bộ não"**: lưu dữ liệu, gọi AI sinh testcase, điều khiển AI Agent, chấm kết quả.
- **App là "tay chân"**: giao diện cho tester, điều khiển trình duyệt thật trên máy tester.
- **Trình duyệt chạy trên máy tester**, nên test được cả web nội bộ, staging, VPN mà server bên ngoài không truy cập được.
- **Local-first**: dữ liệu lưu trên máy trước (SQLite), làm việc được khi mất mạng, có mạng thì đồng bộ lên server.

## 6. Liên hệ lý thuyết môn học

| Khái niệm trong môn học | Thể hiện trong CWTestAgent |
|---|---|
| Kiểm thử hộp đen | Chỉ dựa vào đặc tả và kết quả trên giao diện, không cần mã nguồn. |
| Phân tích giá trị biên, phân vùng tương đương | Đóng gói trong component viewpoint: min−1, min, max, max+1, để trống… |
| Quy trình kiểm thử | Phân tích (khai báo spec) → thiết kế (sinh testcase) → thực thi (chạy) → báo cáo (OK/NG). |
| Kiểm thử hồi quy | Testcase có sẵn, chạy lại toàn bộ sau mỗi bản phát hành bằng 1 nút. |
| Test oracle | Kết quả kỳ vọng lấy từ viewpoint, đối chiếu với thông báo thực tế trên trang. |
| Truy vết và bằng chứng | Mỗi testcase gắn với task, field và viewpoint; lưu ảnh trước/sau và lịch sử chạy. |
| Review testcase | AI thứ hai kiểm duyệt độ phủ của testcase, chưa đạt thì sinh lại (tối đa 3 lần). |

## 7. Cài đặt và chạy thử

Hướng dẫn chi tiết từng bước (biến môi trường, lỗi thường gặp) nằm trong [`SETUP.md`](SETUP.md). Tóm tắt như sau.

**Yêu cầu:** Python 3.11 (server) và 3.13 (app), Docker Desktop, một tài khoản ChatGPT.

**Server** (repo [KiemDinhPhanMem_server](https://github.com/nguyenquangpen/KiemDinhPhanMem_server)), mỗi lệnh một terminal:

```bash
docker compose up -d mongodb redis          # MongoDB + Redis
python -m chatgpt_web.login                 # đăng nhập ChatGPT (chỉ lần đầu)
python -m chatgpt_web.gateway               # cổng gọi ChatGPT, giữ cửa sổ Chrome mở
python main.py                              # API: http://localhost:8765
python -m celery -A celery_config.celery_app worker --pool=solo --loglevel=info --queues=testcase_generation,maintenance
```

**App** (repo này):

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env                        # API_ENDPOINT=http://localhost:8765
python tools/genui.py                       # sinh file giao diện (lần đầu)
python src/main.py                          # mở app
```

App không có màn hình đăng nhập: app tự đăng nhập server bằng tài khoản demo trong `.env`.

### Chạy demo nhanh với dữ liệu mẫu

Repo có sẵn trang web mẫu (đăng ký, đăng nhập, thêm người dùng, thanh toán), trong đó **cố ý cài sẵn một số lỗi** để công cụ phát hiện.

```bash
python -m http.server 8000 -d tools/demo_site   # trang mẫu: http://localhost:8000/login.html
python tools/seed_demo_data.py                  # nạp 3 project, 5 task, 53 testcase và chạy thử
python src/main.py
```

Script `seed_demo_data.py` chạy thật 49 testcase trên trang mẫu. Kết quả mong đợi là **45 OK, 4 NG**: đúng 4 lỗi đã cài sẵn, ví dụ CVV 4 chữ số vẫn thanh toán được. DB cũ được tự sao lưu thành `agent_local_storage.db.bak-<thời gian>`.

## 8. Cấu trúc thư mục

```
src/
├── main.py              # điểm khởi chạy app
├── views/               # các màn hình: Project, Task, Viewpoint, Testcase, đồng bộ
├── models/database.py   # dữ liệu cục bộ SQLite + gọi API server
├── services/
│   ├── api/             # gọi HTTP API của server
│   ├── element_picker.py      # bước 5: click chọn field trên trang
│   ├── quick_runner.py        # runner nhanh: điền form, submit, chấm OK/NG
│   └── websocket_agent_runner.py  # chạy AI Agent qua WebSocket
├── cwagent/             # phần điều khiển trình duyệt cho AI Agent (Playwright)
└── theme/, ui/, asset/  # giao diện (.ui, stylesheet, icon, font)
tools/
├── demo_site/           # trang web mẫu để demo
├── seed_demo_data.py    # nạp dữ liệu demo
└── genui.py, build.py   # sinh file giao diện, đóng gói .exe
```

## 9. Hạn chế và hướng phát triển

| Hạn chế | Hướng phát triển |
|---|---|
| AI có thể chấm sai (bài toán test oracle), nên tester vẫn cần xem lại; mỗi kết quả có ảnh để đối chiếu. | Chấm bằng so khớp thông báo lỗi trước, chỉ dùng AI khi không chắc. |
| ChatGPT bản web chậm hơn API (mỗi lần gọi khoảng 10–30 giây), và phải cập nhật khi chatgpt.com đổi giao diện. | Chuyển sang OpenAI API chỉ bằng đổi biến `LLM_BACKEND` trên server. |
| Runner nhanh chỉ phù hợp kiểu điền form rồi Submit; luồng nhiều bước phải dùng AI Agent (chậm hơn). | Ghi lại luồng nhiều bước (đăng nhập, mở popup…) bằng click, giống bước chọn field. |
| Chưa chạy tự động theo bản build. | Tích hợp CI/CD: tự chạy hồi quy mỗi bản build, xuất báo cáo tổng hợp. |

## 10. Tài liệu thêm

- [`SETUP.md`](SETUP.md): cài đặt và chạy chi tiết, xử lý lỗi thường gặp.
- [`TESTAGENT_TOOL_LOGIC_OVERVIEW.md`](TESTAGENT_TOOL_LOGIC_OVERVIEW.md): logic bên trong app và giao thức giữa app với server.
- Repo server: https://github.com/nguyenquangpen/KiemDinhPhanMem_server
