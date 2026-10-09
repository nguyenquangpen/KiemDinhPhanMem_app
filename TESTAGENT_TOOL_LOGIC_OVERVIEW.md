# testagent-tool - Tài liệu logic client/backend integration

Tài liệu này mô tả repo `testagent-tool` ở góc nhìn logic nghiệp vụ và logic tích hợp với backend `cwtestagent`.

Theo yêu cầu, tài liệu chủ động bỏ qua:

- Auth/security/author logic.
- UI PySide/PyQt chi tiết trong `src/views`, `src/theme`, `src/asset`.
- Thiết kế giao diện, stylesheet, icon, `.ui` files.

Trọng tâm tài liệu là:

- Client service layer gọi backend.
- Local data/cache/sync logic.
- DTO/schema mapping giữa tool và backend.
- Agent executor chạy browser local qua Playwright.
- WebSocket protocol giữa tool và backend agent server.
- Các điểm logic cần biết để hoàn thiện với backend `cwtestagent`.

## 1. Repo này là gì?

`testagent-tool` là desktop client/tool cho hệ thống CWTestAgent. Backend `cwtestagent` chịu trách nhiệm API, LLM testcase generation và agent decision loop; còn `testagent-tool` đóng vai trò client local:

- Quản lý dữ liệu local bằng SQLite.
- Gọi HTTP API của backend để đồng bộ project/task/testcase/viewpoint/template.
- Gửi/nhận sync log với backend.
- Kết nối WebSocket tới backend để chạy testcase bằng agent.
- Mở browser local bằng Playwright.
- Thu thập browser state, DOM tree, screenshot.
- Thực thi action do backend agent gửi xuống.
- Lưu kết quả chạy testcase, screenshot count, checkpoint/session state vào local DB để sync lại.

Nói ngắn gọn: `cwtestagent` là server/brain, `testagent-tool` là desktop client/browser executor/local cache.

## 2. Công nghệ chính

- Python desktop app.
- PySide6/PyQt6 cho UI, nhưng phần này bị bỏ qua trong tài liệu.
- SQLite local file `agent_local_storage.db`.
- HTTP client: `httpx` async.
- WebSocket client: `websockets`.
- Playwright để điều khiển browser.
- Pydantic cho action/browser model.
- Dataclass DTO cho Project/Task/Testcase/Viewpoint.
- PyInstaller/Inno Setup để build app desktop.

Dependencies chính nằm trong:

- `requirements.txt`
- `pyproject.toml`

## 3. Cấu trúc repo liên quan đến logic

```text
D:\Work\testagent-tool
├── src/
│   ├── main.py
│   ├── settings/
│   │   └── config.py
│   ├── services/
│   │   ├── api/
│   │   │   ├── base.py
│   │   │   ├── project.py
│   │   │   ├── testcase.py
│   │   │   ├── tasks.py
│   │   │   ├── viewpoints.py
│   │   │   ├── template.py
│   │   │   ├── sync.py
│   │   │   ├── utils.py
│   │   │   └── exceptions.py
│   │   ├── websocket_agent_runner.py
│   │   ├── session.py
│   │   ├── logging_config.py
│   │   ├── config.py
│   │   ├── db.py
│   │   └── version.py
│   ├── models/
│   │   ├── data_classes.py
│   │   └── database.py
│   ├── cwagent/
│   │   └── ais/
│   │       ├── agent_run.py
│   │       ├── browser/
│   │       ├── controller/
│   │       └── dom/
│   └── utils.py
├── tools/
├── compile.sh
├── build_setup.iss
├── agent_local_storage.db
├── test_db.json
└── tmp.py
```

Các thư mục/file UI không phân tích sâu:

- `src/views/`
- `src/theme/`
- `src/asset/`

## 4. Runtime configuration

### `src/settings/config.py`

Đây là file cấu hình runtime chính của tool.

Biến môi trường quan trọng:

- `API_ENDPOINT`: endpoint backend chính, mặc định `http://localhost:8765`.
- `API_CW_ENDPOINT`: endpoint phụ cho CW auth/service nếu cần.
- `WS_ENDPOINT`: WebSocket backend, mặc định `ws://localhost:8765`.
- `LOG_LEVEL`: logging level.
- `ENVIRONMENT`: `development`, `production`, `testing`.
- `TIMEZONE`: timezone log.

Điểm nối với backend `cwtestagent`:

- Backend chạy mặc định port `8765`.
- Tool mặc định cũng gọi `http://localhost:8765` và `ws://localhost:8765`.
- WebSocket runner dùng `WS_ENDPOINT/ws/agent_pool/{test_uuid}` đúng với route backend.

### `.env.example`

Chứa biến mẫu:

```text
API_ENDPOINT=
API_CW_ENDPOINT=
WS_ENDPOINT=
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
LOG_LEVEL=INFO
ENVIRONMENT=development
TIMEZONE="Asia/Ho_Chi_Minh"
FEEDBACK_LINK=...
```

`CLIENT_ID/CLIENT_SECRET` thuộc phần auth/security nên không phân tích tiếp.

## 5. Startup logic

### `src/main.py`

Đây là entry point desktop app.

Phần UI bị bỏ qua, nhưng logic khởi tạo đáng chú ý:

- Setup logging bằng `setup_logging_with_env()`.
- Tạo `DataManager` với:
  - SQLite file: `agent_local_storage.db`.
  - API endpoint: `API_ENDPOINT`.
  - CW endpoint: `API_CW_ENDPOINT`.
  - `use_api=True`.
- Khi đóng gói PyInstaller, set `PLAYWRIGHT_BROWSERS_PATH` trỏ vào browser bundle.

`DataManager` vì vậy là object trung tâm giữ toàn bộ local state và service integration cho app.

## 6. Service API layer

Thư mục: `src/services/api`.

Đây là lớp client SDK mỏng bọc các endpoint backend `cwtestagent`.

### `BaseAPI` - `src/services/api/base.py`

`BaseAPI` quản lý HTTP request async bằng `httpx.AsyncClient`.

Method có sẵn:

- `get(path, params=None, headers=None)`
- `post(path, data=None, headers=None, return_status=False)`
- `put(path, data=None, headers=None)`
- `patch(path, data=None, headers=None)`
- `delete(path, headers=None)`

Đặc điểm:

- URL được ghép dạng `endpoint/path`.
- Timeout đang để `100` giây.
- Nếu HTTP error thì log lỗi và trả `None`.
- Riêng `post(..., return_status=True)` trả tuple `(json, status_code)`.

### `ProjectService` - `project.py`

Gọi các endpoint project backend:

| Method client | Backend endpoint |
|---|---|
| `create_project` | `POST api/projects` |
| `get_project` | `GET api/projects/{project_id}` |
| `patch_update_project` | `PATCH api/projects/{project_id}` |
| `delete_project` | `DELETE api/projects/{project_id}` |
| `list_projects` | `GET api/projects` |

Dữ liệu tương ứng với `ProjectCreateModel`/`ProjectUpdateModel` bên backend.

### `TestCaseService` - `testcase.py`

Gọi testcase endpoint backend:

| Method client | Backend endpoint |
|---|---|
| `create_test_case` | `POST api/testcases?project_id={project_id}` |
| `get_test_cases` | `GET api/testcases?project_id=...&task_id=...` |
| `update_test_case` | `PUT api/testcases/{test_case_id}` |
| `delete_test_case` | `DELETE api/testcases/{test_case_id}` |

Tool lấy testcase theo cả `project_id` và `task_id`, trùng với backend `get_prj_testcases_view`.

### `TaskService` - `tasks.py`

Gọi task/generation endpoint backend:

| Method client | Backend endpoint |
|---|---|
| `list_tasks` | `GET api/tasks/by_project?project_id=...` |
| `create_task` | `POST api/tasks` |
| `get_task` | `GET api/tasks/{task_id}` |
| `update_task` | `PUT api/tasks/{task_id}` |
| `delete_task` | `DELETE api/tasks/{task_id}` |
| `generate_testcases` | `POST api/tasks/{task_id}/generate-testcases` |
| `get_generation_status` | `GET api/tasks/{task_id}/generation-status` |
| `get_background_task_status` | `GET api/background-tasks/{celery_task_id}/status` |

Đây là service kết nối trực tiếp với Celery generation flow của backend.

### `ViewpointsService` - `viewpoints.py`

Gọi viewpoint endpoint backend:

| Method client | Backend endpoint |
|---|---|
| `create_viewpoint` | `POST api/viewpoints` |
| `update_viewpoint` | `PATCH api/viewpoints/{viewpoint_id}/bulk-update` |
| `delete_viewpoint` | `DELETE api/viewpoints/{viewpoint_id}` |
| `list_viewpoints` | `GET api/viewpoints?project_id=...` |
| `get_viewpoint_choices` | `GET api/vp_choices` |

Ghi chú logic: `get_viewpoint` đang gọi `GET api/viewpoints/{viewpoint_id}`, nhưng backend hiện tại không có route GET chi tiết viewpoint theo id. Tool phần lớn dùng local SQLite để lấy viewpoint chi tiết, nên lỗi này có thể chưa lộ ra trong luồng chính.

### `TemplateService` - `template.py`

Gọi template endpoint backend:

| Method client | Backend endpoint |
|---|---|
| `create_templates` | `POST api/templates` |
| `get_template` | `GET api/templates/{template_id}` |
| `list_templates` | `GET api/templates/` |
| `update_templates` | `PATCH api/templates/{template_id}` |
| `delete_templates` | `DELETE api/templates/{template_id}` |
| `clone_templates` | `POST api/templates/clone` |

Ghi chú tương thích backend:

- Backend template create route là `/api/templates/`; FastAPI thường xử lý slash linh hoạt, nhưng nên thống nhất.
- Backend update template hiện là `PUT /api/templates/{template_id}`, trong khi client dùng `PATCH`. Đây là điểm lệch cần sửa nếu dùng API template update thật.
- `clone_templates` nhận `template_data` nhưng không truyền `data=template_data` vào `post`, nên hiện clone request thiếu body.

### `SyncService` - `sync.py`

Gọi sync endpoint backend:

| Method client | Backend endpoint |
|---|---|
| `push_sync_data` | `POST api/sync/push` |
| `get_snapshot` | `GET api/sync/snapshot` |
| `pull_sync_data` | `GET api/sync/pull?since=...` |

Ghi chú tương thích backend:

- Backend có `GET /api/sync/pull` đúng.
- Backend route snapshot trong code hiện viết `@sync_router.get("sync/snapshot")`, thiếu slash, nên client `api/sync/snapshot` có thể không match.

### `utils.py` và `exceptions.py`

Có helper:

- Build headers.
- Format URL.
- Parse JSON response.
- Handle HTTP status thành exception.
- Log request/response.

Phần token/auth header thuộc nhóm bảo mật nên không phân tích sâu.

## 7. DTO/schema mapping

File: `src/models/data_classes.py`.

Đây là lớp chuyển đổi giữa dữ liệu backend, local DB và object trong app.

### Enum chính

- `TestcaseStatus`: `PENDING`, `PASSED`, `FAILED`, `BLOCKED`, `SKIPPED`.
- `ViewpointType`: `PAGE = "page"`, `COMPONENT = "component"`.
- `TaskStatus`: trạng thái Celery như `PENDING`, `STARTED`, `FAILURE`, `SUCCESS`, `RUNNING`.

### `Project`

Map với project backend.

Field chính:

- `project_id` map từ backend `uuid`.
- `name`, `url`, `description`.
- `login_id`, `password` dùng cho task cần login.
- `tasks`.
- `testcase_specification`.
- `testcase_generated`.
- `created_at`, `updated_at`, `created_by`.

Có property thống kê:

- `total_testcase_count`
- `executed_testcase_count`
- `ok_testcase_count`
- `ng_testcase_count`

### `Task`

Map với task backend.

Field chính:

- `task_id` map từ backend `uuid`.
- `task_name`.
- `url_test`.
- `viewpoint_id`.
- `project_id`.
- `request_login`.
- `specs` map sang backend `items`.
- `celery_task_id`.
- `generation_status`.
- `include_component_viewpoints`.

`Task.to_dict()` xuất cả `specs` và `items`, trong đó `items` là field backend dùng.

### `Spec`

Map với item/spec trong backend task.

Field local:

- `name`
- `required`
- `min`
- `max`
- `specification`
- `default_value`
- `validation_types`

Khi gửi backend:

- `name` -> `item_name`
- `specification` -> `spec`
- `default_value` -> `default`

### `Viewpoint` và `ViewpointDescription`

Map với viewpoint backend.

`ViewpointDescription`:

- `description_input`
- `error_message_expected`
- `final_result_expected`
- `detail_id`

`Viewpoint`:

- `name`
- `viewpoint_type`
- `viewpoint_details`
- `viewpoint_id` map backend `uuid`
- `project_id`

### `Testcase`

Map với testcase backend.

Field backend chính:

- `test_field`
- `test_type`
- `test_case`
- `test_reference`
- `test_expect`
- `test_status`

Mapping status:

- Local `PENDING` -> backend `not_started`.
- Local `PASSED` -> backend `is_done`.
- Local `FAILED/BLOCKED` -> backend `is_error`.

### Execution/report models

- `Screenshot`: metadata ảnh chụp khi chạy test.
- `TestExecutionResult`: kết quả một lần chạy testcase.
- `TestReport`: thống kê kết quả chạy theo project.

Các object này chủ yếu phục vụ local result/report và update lại testcase.

## 8. DataManager - local source of truth

File: `src/models/database.py`.

`DataManager` là class quan trọng nhất của client. Nó quản lý:

- SQLite connection.
- Local project/task/testcase/viewpoint/template data.
- Current project/current task.
- API service instances.
- Sync log.
- Signals để UI refresh.
- Testcase generation request.
- Lưu kết quả agent execution.

### 8.1 SQLite tables

`DataManager._create_tables()` tạo các bảng:

- `users`
- `projects`
- `tasks`
- `viewpoints`
- `testcases`
- `sync_log`
- `sync_settings`
- `viewpoints_templates`

Bảng nghiệp vụ quan trọng:

#### `projects`

Lưu project local:

- `uuid`
- `user_id`
- `name`
- `url`
- `description`
- `login_id`
- `password`
- `testcase_specification`
- `created_at`, `updated_at`
- `testcase_generated`

#### `tasks`

Lưu task local:

- `uuid`
- `project_id`
- `task_name`
- `url_test`
- `viewpoint_id`
- `request_login`
- `specs_json`
- `celery_task_id`
- `generation_status`
- `include_component_viewpoints`
- `generation_completed_at`
- `generation_error`
- `testcases_generated`
- `status`

#### `viewpoints`

Lưu viewpoint local:

- `uuid`
- `project_id`
- `name`
- `viewpoint_type`
- `description`
- `details_json`
- `created_at`, `updated_at`

#### `testcases`

Lưu testcase local:

- `uuid`
- `task_uuid`
- `project_id`
- `test_field`
- `test_type`
- `test_case`
- `test_reference`
- `test_expect`
- `test_status`
- `last_run_status`
- `last_run_time`
- `test_result_details`
- `checkpoint_data`
- `step_number`

`checkpoint_data` và `step_number` là phần quan trọng cho resume agent execution.

#### `sync_log`

Lưu operation pending để push lên backend:

- `operation_type`
- `table_name`
- `record_uuid`
- `payload`
- `timestamp`
- `sync_status`

#### `sync_settings`

Lưu cấu hình sync local:

- `enabled`
- `auto_sync`
- `interval_sync`
- `interval_ms`
- `last_pull_at`

#### `viewpoints_templates`

Lưu template viewpoint local:

- `uuid`
- `name`
- `viewpoint_type`
- `viewpoint_details`
- `created_at`, `updated_at`

### 8.2 Sync log compaction

`_compact_logs()` gom nhiều log local thành batch tối giản trước khi push:

- `CREATE` sau đó `UPDATE` -> vẫn là `CREATE`, payload merge.
- `CREATE` sau đó `DELETE` -> bỏ luôn vì record chưa cần lên server.
- `UPDATE` sau đó `UPDATE` -> merge payload.
- `UPDATE` sau đó `DELETE` -> thành `DELETE`.
- `DELETE` sau đó `CREATE` -> thành `UPDATE`.

Ý nghĩa: giảm số request và tránh gửi các thay đổi thừa.

### 8.3 Push local changes

`push_local_changes()`:

1. Lấy tất cả `sync_log` trạng thái `pending`.
2. Compact logs.
3. Sanitize payload, bỏ các field local như `id`, `created_by`, `user_id`, `_id`.
4. Gửi batch qua `SyncService.push_sync_data()` -> backend `/api/sync/push`.
5. Nếu status `200` hoặc `202`, xóa log local đã xử lý.

### 8.4 Pull remote data

`pull_remote_data()`:

1. Đọc `last_pull_at` từ `sync_settings`.
2. Gọi backend `/api/sync/pull?since=...`.
3. Chạy transaction SQLite.
4. Upsert projects, tasks, viewpoints, testcases vào local DB.
5. Cập nhật `last_pull_at` bằng `new_timestamp` từ backend.

Đây là cơ chế delta sync để client có thể offline/cache local rồi đồng bộ sau.

### 8.5 Project logic

Các method chính:

- `get_all_projects()`
- `get_project_by_id()`
- `add_project()`
- `delete_project()`
- `patch_update_project()`
- `update_project_specifications()`
- `set_current_project()`

Điểm đáng chú ý:

- Project tạo mới ở local trước, sinh UUID local bằng `uuid.uuid4()`.
- Mọi create/update/delete đều ghi `sync_log` để push sau.
- `testcase_specification` được lưu JSON string trong SQLite.

### 8.6 Task logic

Các method chính:

- `list_tasks(project_id)`
- `create_task(task_data, project_id)`
- `get_task(task_id)`
- `update_task(task_id, task_data)`
- `delete_task(task_id)`
- `set_current_task(task_id)`

Điểm đáng chú ý:

- Task lưu `items/specs` thành JSON trong cột `specs_json`.
- `include_component_viewpoints` lưu dạng integer 0/1.
- Create/update/delete cũng ghi sync log.

### 8.7 Testcase logic

Các method chính:

- `create_test_case(test_case_data)`
- `get_test_cases(project_id, task_id=None)`
- `update_test_case(test_case_id, test_case_data)`
- `delete_test_case(test_case_id)`
- `save_test_execution_result(execution_result)`
- `get_test_execution_results(project_id)`

Khi tạo testcase local:

- Sinh `uuid` mới.
- Set `test_status = "not_started"`.
- Tự gắn `task_uuid` từ current task nếu payload không có.
- Tự gắn `project_id` từ current project nếu payload không có.
- Lưu `test_result_details` dạng JSON.
- Ghi sync log `CREATE`.

Khi lưu kết quả chạy testcase:

1. Tìm testcase theo `testcase_id`.
2. Lấy `test_result_details` hiện tại.
3. Append một history item mới gồm:
   - `status`
   - `start_time`
   - `end_time`
   - `error_message`
   - `screenshots_count`
   - `execution_id`
   - `duration`
4. Map client status sang backend enum:
   - `passed/completed` -> `is_done`
   - `failed/error` -> `is_error`
   - còn lại -> `not_started`
5. Lưu thêm:
   - `last_run_status`
   - `last_run_time`
   - `checkpoint_data`
   - `step_number`
6. Gọi `update_test_case()`, đồng thời ghi sync log update.

### 8.8 Viewpoint logic

Các method chính:

- `create_viewpoint()`
- `get_viewpoints(project_id)`
- `get_viewpoint(viewpoint_id)`
- `update_viewpoint(viewpoint_id, viewpoint_data)`
- `delete_viewpoint(viewpoint_id)`

Client lưu viewpoint local theo project. `viewpoint_details` được serialize vào cột `details_json`.

### 8.9 Template logic local

Các method chính:

- `save_or_update_template(template_data)`
- `list_templates(viewpoint_type)`
- `delete_template(template_id)`

Template được lưu ở bảng local `viewpoints_templates`. Hiện `save_or_update_template` có logic `is_new = not bool(template_data.get("uuid"))`, nhưng sau đó không sinh UUID nếu thiếu. Nếu gọi tạo mới mà không có `uuid`, record có thể lỗi/không đúng vì `uuid` là primary key.

## 9. Luồng sinh testcase từ client sang backend

Method chính: `DataManager.generate_testcases()`.

Luồng chi tiết:

1. Client nhận `task_id` và options:
   - `force_regenerate`
   - `include_component_viewpoints`
2. Lấy task local từ SQLite.
3. Lấy project local tương ứng.
4. Chuẩn hóa `project_details` thành dict.
5. Parse `testcase_specification` nếu đang là JSON string.
6. Lấy main viewpoint local từ `task_data["viewpoint_id"]`.
7. Bỏ các field local không cần gửi backend như `project_id`, `created_by`, `description` trong viewpoint payload.
8. Nếu bật component viewpoint:
   - Duyệt từng item trong task.
   - Lấy `validation_types`.
   - Gom UUID component viewpoint.
   - Load từng component viewpoint local.
   - Đưa vào dict `component_viewpoints`.
9. Build payload gửi backend:

```json
{
  "url_test": "...",
  "task_name": "...",
  "viewpoint_data": {},
  "project_details": {},
  "request_login": true,
  "items": [],
  "uuid": "task_id",
  "generation_status": "...",
  "include_component_viewpoints": true,
  "force_regenerate": true,
  "component_viewpoints": {}
}
```

10. Gọi `TaskService.generate_testcases()` -> backend `/api/tasks/{task_id}/generate-testcases`.
11. Backend Celery sinh testcase.
12. Client gọi `get_generation_status()` để poll.
13. Nếu backend trả `generation_status == "completed"` và có `generated_testcases`, client gọi `save_generated_testcases_locally()`.
14. Local DB xóa testcase cũ theo task rồi insert testcase mới.
15. Task local được update generation fields.

Đây là luồng rất quan trọng vì backend `cwtestagent` đang kỳ vọng payload dạng này trong `celery_tasks.py`.

## 10. Lưu testcase sinh ra từ backend

Method: `save_generated_testcases_locally(task_uuid, testcases)`.

Luồng:

1. Tìm `project_id` local từ bảng `tasks`.
2. Xóa testcase cũ của `task_uuid`.
3. Với mỗi testcase backend trả:
   - Lấy `uuid`, hoặc sinh UUID nếu thiếu.
   - Gắn `task_uuid`.
   - Resolve `project_id`.
   - Lưu `test_field`, `test_type`, `test_case`, `test_reference`, `test_expect`.
   - Set `test_status = "not_started"`.
4. Commit SQLite.

Điểm nối backend:

- Backend Celery hiện đang trả `generated_testcases` trong temp task status thay vì insert trực tiếp vào `testcases_collection` ở một số đoạn. Client vì vậy tự lưu danh sách đó vào SQLite local.

## 11. Agent executor qua WebSocket

Có hai lớp chính:

- `src/services/websocket_agent_runner.py`
- `src/cwagent/ais/agent_run.py`

### 11.1 `EnhancedAgentTestRunner`

File: `src/services/websocket_agent_runner.py`.

Vai trò:

- Khởi tạo browser config.
- Tạo `Browser` và `Agent` local.
- Chạy một hoặc nhiều testcase.
- Trả execution result chuẩn cho DataManager lưu lại.
- Cho phép stop execution.

Cấu hình browser mặc định:

```python
BrowserConfig(
    headless=headless,
    disable_security=True,
    deterministic_rendering=True,
)
```

Logic chính:

- `execute_single_test_case_websocket(test_data, on_step_update=None)`:
  - Lấy testcase id/name.
  - Tạo result object ban đầu.
  - Gọi `initialize()` để tạo Agent local.
  - Gọi `run_agent_with_test_case()`.
  - Nhận `result_images` và `action_result`.
  - Set status:
    - user stop -> `cancelled`
    - có action_result -> `passed`
    - không có action_result -> `failed`
  - Gắn `checkpoint_data` nếu Agent có.
  - Trả dict execution result.

- `stop_execution()`:
  - Gọi `runner.graceful_stop()`.
  - Agent gửi cancel signal lên server.

### 11.2 `Agent` local executor

File: `src/cwagent/ais/agent_run.py`.

Đây là agent phía client. Nó không quyết định bằng LLM; nó nhận action từ backend và thực thi bằng Playwright.

Luồng `Agent.run()`:

1. Connect WebSocket:

```text
{WS_ENDPOINT}/ws/agent_pool/{test_uuid}
```

2. Gửi message init:

```json
{
  "type": "init",
  "payload": "test_context"
}
```

3. Đợi backend trả status `Done`.
4. Gửi message run:

```json
{ "type": "run" }
```

5. Vào loop nhận message từ backend:

- `status == "request_state"`
  - Client lấy browser state bằng `browser_context.get_state()`.
  - Serialize state bằng `pickle.dumps`.
  - Gửi bytes lên backend.

- `status == "server_actions"`
  - Client nhận danh sách actions từ backend.
  - Gọi `multi_act(actions)` để thực thi.

- `status == "request_action_results"`
  - Client gửi lại `action_results` dạng JSON.

- `status == "checkpoint"`
  - Client nhận `agent_state` base64 từ backend.
  - Lấy current URL.
  - Lấy browser `storage_state`.
  - Lưu thành `checkpoint_data` gồm:
    - `agent_state`
    - `session_state`
    - `current_url`
    - `step_number`

- `status == "restore_session"`
  - Client restore browser context từ `session_state`.
  - Điều hướng lại `current_url`.
  - Gửi một action result báo restore thành công.

- `status == "testcase_done"`
  - Kết thúc loop.

6. Cleanup WebSocket/browser.
7. Trả `(result_images, action_result)`.

### 11.3 `multi_act()`

`multi_act()` thực thi từng action backend gửi:

1. Remove highlight cũ.
2. Lấy current page.
3. Duyệt từng action.
4. Gọi `controller.act(action, browser_context)`.
5. Lưu result.
6. Chụp screenshot full page sau mỗi action.
7. Base64 encode screenshot và thêm vào `result_images`.
8. Nếu action `done` hoặc lỗi, dừng action loop.

Đây là nơi screenshot count và execution evidence được tạo.

## 12. Browser automation layer

Thư mục: `src/cwagent/ais/browser`.

### `browser.py`

Quản lý Playwright browser process.

Class chính:

- `BrowserConfig`
- `Browser`

`BrowserConfig`:

- `browser_class`: mặc định `chromium`.
- `browser_binary_path`: dùng browser cài sẵn nếu có.
- `headless`.
- `disable_security`.
- `deterministic_rendering`.
- `keep_alive`.
- `new_context_config`.

`Browser`:

- Start Playwright.
- Nếu có `browser_binary_path`, connect Chrome qua CDP port `9222`.
- Nếu không, launch browser builtin của Playwright.
- Tính window size theo monitor.
- Apply Chrome args.
- Cleanup browser/playwright/httpx clients.

### `chrome.py`

Định nghĩa Chrome launch args.

Theo yêu cầu, không phân tích sâu phần disable security. Với logic test, ý nghĩa chính là làm browser ổn định hơn cho automation và screenshot.

### `context.py`

`BrowserContext` là lớp phức tạp nhất của browser executor.

Chức năng chính:

- Tạo browser context/tab.
- Lấy current page.
- Chờ network/page ổn định.
- Lấy browser state cho backend.
- Build DOM state.
- Chụp screenshot.
- Quản lý tabs.
- Locate/click/input element.
- Restore storage/session state.
- Cung cấp một số helper test webapp.

Method đáng chú ý:

- `get_state()` -> trả `BrowserState` gồm DOM tree, selector map, URL, title, tabs, screenshot, scroll info.
- `_update_state()` -> build DOM state bằng `DomService`, chụp screenshot, lấy tabs.
- `take_screenshot()` -> screenshot base64, có thể annotate.
- `get_session_state()` -> lấy Playwright storage state, phục vụ checkpoint/resume.
- `remove_highlights()` -> xóa overlay highlight khỏi page.
- `get_locate_element_by_xpath/css_selector/text()` -> tìm element.
- `_input_text_element_node()` -> nhập text vào DOM element.
- `_click_element_node()` -> click DOM node, xử lý file upload/download/new tab.
- `get_tabs_info()`, `switch_to_tab()`, `create_new_tab()`.
- `get_selector_map()`, `get_dom_element_by_index()`.
- `is_file_uploader()`.
- Helper test webapp: navigate, wait, click selector, type, fill form, select option, verify element/text/title/url, scroll, console errors, page load time, responsive, accessibility basics.

Điểm khớp backend:

- Backend agent yêu cầu browser state qua WebSocket.
- Client gửi `pickle` của `BrowserState`.
- Backend prompt dùng DOM text/selector map để chọn action.
- Client dùng action model để thực thi action.

## 13. DOM extraction layer

Thư mục: `src/cwagent/ais/dom` và `src/utils.py`.

### `src/utils.py`

Chứa `build_domtree_js`, một đoạn JavaScript lớn inject vào page để build DOM tree.

Logic JS chính:

- Duyệt DOM từ `document.body`.
- Bỏ qua script/style/svg/meta/template và node không cần thiết.
- Nhận diện interactive elements:
  - `a`, `button`, `input`, `select`, `textarea`, `details`, `summary`, `label`, `option`, ...
  - Role như `button`, `menuitem`, `radio`, `checkbox`, `tab`, `switch`, `slider`, `combobox`, `textbox`, `listbox`, ...
  - Một số class/attribute như dropdown, data-index, aria-haspopup.
- Kiểm tra visibility/top element/in viewport.
- Gán `highlightIndex` cho interactive element.
- Vẽ overlay highlight trên page.
- Traverse iframe và shadow DOM nếu có thể.
- Trả về `rootId` và `map`.

### `DomService` - `dom/views.py`

`DomService` chạy `build_domtree_js` trên Playwright page và convert kết quả JS thành Python objects.

Method chính:

- `get_clickable_elements()`
- `_build_dom_tree()`
- `_construct_dom_tree()`
- `_parse_node()`

Output là `DOMState` gồm:

- `element_tree`
- `selector_map`: map `highlight_index -> DOMElementNode`

### `dom/models.py`

Model DOM:

- `DOMElementNode`
- `DOMTextNode`
- `DOMState`
- `SelectorMap`
- `CoordinateSet`
- `ViewportInfo`

`DOMElementNode.get_all_text_till_next_clickable_element()` gom text liên quan đến element, giúp action result và prompt mô tả element dễ hiểu hơn.

## 14. Controller/action executor

Thư mục: `src/cwagent/ais/controller`.

### `controller/models.py`

Định nghĩa action schema mà backend có thể gửi xuống client:

- `GoToUrlAction`
- `WaitForElementAction`
- `ClickElementAction`
- `ClickElementByXpathAction`
- `ClickElementBySelectorAction`
- `ClickElementByTextAction`
- `InputTextAction`
- `DoneAction`
- `SwitchTabAction`
- `OpenTabAction`
- `CloseTabAction`
- `ScrollAction`
- `SendKeysAction`
- `DragDropAction`
- `ActionResult`

### `controller/views.py`

`Controller` đăng ký và thực thi action.

Action chính:

- `done`: kết thúc testcase.
- `go_to_url`: điều hướng URL.
- `go_back`: quay lại.
- `wait`: chờ.
- `wait_for_element`: chờ selector visible.
- `click_element_by_index`: click element theo selector map index.
- `click_element_by_selector`: click CSS selector.
- `click_element_by_xpath`: click XPath.
- `click_element_by_text`: click theo text.
- `input_text`: nhập text vào element index.
- `switch_tab`: chuyển tab.
- `open_tab`: mở tab.
- `close_tab`: đóng tab.
- `extract_content`: trích nội dung page.
- `scroll_down`, `scroll_up`, `scroll_to_text`.
- `send_keys`.
- `get_dropdown_options`.
- `select_dropdown_option`.
- `drag_drop`.

`Controller.act(action, browser_context)` nhận action dict từ backend, xác định action name/params, rồi gọi function tương ứng.

Điểm khớp backend:

- Backend `cwtestagent` cũng có controller/action schema gần tương tự.
- Server sinh action theo schema; client thực thi action bằng Playwright thật.
- Nếu hai repo lệch schema action, WebSocket agent sẽ lỗi.

## 15. WebSocket protocol giữa hai repo

### Backend route

Backend `cwtestagent`:

```text
/ws/agent_pool/{testcase_id}
```

### Client connect

Client `testagent-tool`:

```text
{WS_ENDPOINT}/ws/agent_pool/{test_uuid}
```

### Message từ client lên server

Init:

```json
{
  "type": "init",
  "payload": {
    "test_case": {},
    "project": {},
    "task": {},
    "checkpoint_data": {}
  }
}
```

Run:

```json
{ "type": "run" }
```

Action results:

```json
{
  "action_results": [
    {
      "is_done": false,
      "success": null,
      "extracted_content": "...",
      "error": null,
      "include_in_memory": true
    }
  ]
}
```

Cancel:

```json
{
  "status": "cancelled",
  "reason": "user clicked stop"
}
```

Browser state:

- Gửi dạng bytes bằng `pickle.dumps(BrowserState)`.

### Message từ server xuống client

Server init OK:

```json
{ "status": "Done" }
```

Yêu cầu browser state:

```json
{ "status": "request_state" }
```

Gửi action:

```json
{
  "status": "server_actions",
  "data": [],
  "step_number": 3
}
```

Yêu cầu action results:

```json
{ "status": "request_action_results" }
```

Checkpoint:

```json
{
  "status": "checkpoint",
  "agent_state": "base64...",
  "step_number": 3
}
```

Restore session:

```json
{
  "status": "restore_session",
  "data": {
    "session_state": {},
    "current_url": "..."
  }
}
```

Done:

```json
{ "status": "testcase_done" }
```

## 16. Checkpoint/resume logic

Checkpoint nằm ở cả server và client.

Client khi nhận `checkpoint`:

1. Lấy `agent_state` server gửi.
2. Lấy current URL từ browser.
3. Lấy Playwright storage state bằng `browser_context.get_session_state()`.
4. Lưu object:

```json
{
  "agent_state": "base64...",
  "session_state": {},
  "current_url": "...",
  "step_number": 3
}
```

`EnhancedAgentTestRunner` đưa `checkpoint_data` này vào execution result.

`DataManager.save_test_execution_result()` lưu `checkpoint_data` vào cột testcase.

Lần chạy sau, UI/client có thể gửi `checkpoint_data` trong `test_context` khi init agent. Backend sẽ inject checkpoint vào agent history và gửi `restore_session` về client. Client restore browser context rồi tiếp tục.

Đây là cơ chế giúp resume testcase sau cancel/error/disconnect.

## 17. Logging

File: `src/services/logging_config.py`.

Logger chính:

- `testagent`
- `testagent.api`
- `testagent.agent`
- `testagent.database`
- `testagent.ui`
- `testagent.session`

File log:

- `logs/testagent.log`
- `logs/api.log`
- `logs/agent.log`
- `logs/errors.log`

Formatter agent dùng ISO timestamp theo timezone cấu hình.

## 18. Build/package logic

### `tools/build.py`

Build desktop app bằng PyInstaller:

- Chạy từ thư mục `src`.
- Set `PLAYWRIGHT_BROWSERS_PATH=0`.
- Add data:
  - icons
  - asset
  - `.env`
  - Playwright browser bundle từ `%LOCALAPPDATA%/ms-playwright`
- Output vào `dist/App`.
- Sau build, move `.env` từ `_internal/.env` ra cạnh app exe.

### `compile.sh`

Compile UI `.ui` và resource `.qrc`. Vì UI bị bỏ qua, chỉ cần biết script này phục vụ generate UI Python files.

### `build_setup.iss`

Script Inno Setup để đóng gói installer Windows.

## 19. File phụ/nháp

### `tmp.py`

Script thử nghiệm/nháp thao tác trực tiếp SQLite checkpoint:

- Mở `agent_local_storage.db`.
- Đọc `test_db.json`.
- Update `step_number` và `checkpoint_data` cho một testcase UUID hard-code.
- Phần comment phía dưới thử nghiệm Playwright storage state restore.

Không nên xem đây là runtime chính.

### `test_db.json`

Dữ liệu test/debug cho checkpoint hoặc state.

### `agent_local_storage.db`

SQLite local runtime database hiện có trong repo. Đây là artifact dữ liệu local, không phải source code.

## 20. Quan hệ với backend `cwtestagent`

Hai repo đang ghép như sau:

```text
              HTTP API                         Mongo/LLM/Celery
 testagent-tool  --------------------------->  cwtestagent backend
      |                                           |
      | WebSocket /ws/agent_pool/{testcase_id}    |
      v                                           v
 Local Playwright browser  <--- actions ---  Backend Agent LLM loop
      |
      +--- browser state / action results / checkpoint ---> backend
```

Backend chịu trách nhiệm:

- Project/task/testcase/viewpoint/template API.
- Sinh testcase bằng LLM/Celery.
- Agent prompt/history/planning/validation.
- Quyết định action tiếp theo.

Tool chịu trách nhiệm:

- Cache local và offline-first data.
- Chuẩn bị payload đầy đủ cho testcase generation.
- Poll generation status.
- Lưu testcase generated vào SQLite.
- Mở browser thật.
- Extract DOM/browser state.
- Thực thi action.
- Chụp screenshot.
- Lưu execution result và checkpoint.
- Push/pull sync với backend.

## 21. Những điểm lệch/tồn tại cần chú ý khi hoàn thiện backend-client

Các điểm này không thuộc auth/security/UI, chỉ là compatibility/logic:

1. `TemplateService.update_templates()` dùng `PATCH api/templates/{template_id}`, nhưng backend hiện dùng `PUT /api/templates/{template_id}`.
2. `TemplateService.clone_templates()` không truyền `template_data` vào body khi gọi `POST api/templates/clone`.
3. `ViewpointsService.get_viewpoint()` gọi `GET api/viewpoints/{viewpoint_id}`, nhưng backend hiện chưa có endpoint này.
4. `SyncService.get_snapshot()` gọi `api/sync/snapshot`, còn backend route snapshot đang thiếu slash trong decorator nên có thể không match.
5. Backend sync push hiện nhận table names như `projects`, `tasks`, `testcases`, `viewpoints`, `users`; client local template sync dùng `viewpoints_templates`, backend hiện chưa map table này trong `get_collection_by_name`.
6. Client `pull_remote_data()` đọc task field `specs_json` từ response, nhưng backend task model trả `items`; đoạn pull hiện dùng `json.dumps(t.get("specs_json", []))`, có thể làm mất items nếu backend không trả `specs_json`.
7. Client local generation flow gửi payload rất giàu thông tin (`viewpoint_data`, `project_details`, `component_viewpoints`), backend Celery hiện đang dựa vào payload này trong `temp_task_collection`. Cần giữ contract này ổn định.
8. Action schema giữa backend và client phải đồng bộ. Hai bên đang khá giống nhau, nhưng nếu thêm action ở backend thì client cũng phải implement execution tương ứng.
9. Browser state gửi bằng pickle qua WebSocket. Đây là contract nội bộ Python-Python, nhưng hai repo phải dùng model tương thích để deserialize/đọc state đúng.
10. `DataManager.save_or_update_template()` không sinh UUID khi template mới thiếu `uuid`, dù table dùng `uuid` primary key.
11. `BaseAPI.post(return_status=True)` trong exception branch có thể tham chiếu `response.status_code` khi `response` chưa tồn tại nếu lỗi xảy ra trước khi response được gán.
12. Có `src/services/db.py` và `src/services/config.py` cho MySQL config, nhưng luồng chính hiện dùng SQLite `DataManager`; phần MySQL trông như scaffold cũ.
13. README vẫn là scaffold PyQt chung, chưa phản ánh đúng logic TestAgent hiện tại.

## 22. Tóm tắt logic quan trọng nhất

Nếu chỉ cần hiểu phần bổ trợ backend, đọc theo thứ tự này:

1. `src/settings/config.py`: endpoint HTTP/WS.
2. `src/services/api/*.py`: client SDK gọi backend.
3. `src/models/data_classes.py`: schema/DTO mapping.
4. `src/models/database.py`: local SQLite, sync, generation payload, result saving.
5. `src/services/websocket_agent_runner.py`: wrapper chạy testcase.
6. `src/cwagent/ais/agent_run.py`: WebSocket executor loop.
7. `src/cwagent/ais/browser/context.py`: browser state/action primitives.
8. `src/cwagent/ais/controller/*`: action schema và execution.
9. `src/cwagent/ais/dom/*` + `src/utils.py`: DOM extraction cho backend agent.

## 23. Kết luận

`testagent-tool` không chỉ là UI desktop. Phần logic chính của nó là một local-first client runtime cho backend `cwtestagent`:

- Backend sinh testcase và quyết định action bằng LLM.
- Tool giữ dữ liệu local, đồng bộ dữ liệu, mở browser, trả state, chạy action, lưu evidence/checkpoint.
- Hai repo phụ thuộc mạnh vào contract endpoint, payload generation, WebSocket message, action schema và model browser state.

Khi hoàn thiện backend, cần xem `DataManager.generate_testcases()`, `Agent.run()`, `BrowserContext.get_state()` và `Controller.act()` là các contract client quan trọng nhất.
