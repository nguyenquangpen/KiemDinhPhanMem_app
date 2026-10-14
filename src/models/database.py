# my_app/models/database.py

import asyncio
import json
import os
import uuid
import sqlite3
import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal as Signal

from models.data_classes import Project, Task, User, ViewpointType
from services.api.auth import AuthService
from services.api.project import ProjectService
from services.api.tasks import TaskService
from services.api.template import TemplateService
from services.api.testcase import TestCaseService
from services.api.viewpoints import ViewpointsService
from services.api.sync import SyncService
from services.logging_config import get_database_logger
from services.session import session_manager
from models.data_classes import ViewpointType

logger = get_database_logger()


class DataManagerSignals(QObject):
    """Container for signals emitted by the DataManager for UI reactivity."""

    project_edited = Signal()
    current_project_changed = Signal(object)
    current_task_changed = Signal(object)
    viewpoints_changed = Signal()
    sync_needed = Signal()
    current_user_changed = Signal(object)


# --- Custom Exceptions for Clarity ---
class DataManagerError(Exception):
    """Base exception for DataManager."""

    pass


class NotAuthenticatedError(DataManagerError):
    """Raised when an operation requires authentication but the user is not logged in."""

    pass


class NoProjectSelectedError(DataManagerError):
    """Raised when an operation requires a project context but none is selected."""

    pass


class DataManager:
    """
    Manages all data for the application, handling loading from and saving to
    a JSON file and/or API endpoints. It acts as the single source of truth for
    projects, users, and the application's current state (e.g., the current project).
    """

    def __init__(
        self,
        db_path: str,
        api_endpoint: Optional[str] = None,
        use_api: bool = False,
    ):
        logger.info(
            "Initializing DataManager with db_path=%s, api_endpoint=%s, use_api=%s",
            db_path,
            api_endpoint,
            use_api,
        )
        self.db_path = db_path
        self.projects: List[Project] = []
        self.users: List[User] = []
        self._projects_by_id: Dict[str, Project] = {}  # Changed to str for project_id
        self.current_project: Optional[Project] = None
        self.current_user_token: Optional[str] = None
        self.current_task: Optional[Task] = None
        self.current_local_user_id: Optional[int] = None

        self.signals = DataManagerSignals()

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()

        # API integration
        self.use_api = use_api
        self.api_endpoint = api_endpoint

        if self.use_api and api_endpoint:
            logger.info("Initializing API services with endpoint: %s", api_endpoint)
            self.auth_service = AuthService(api_endpoint)
            self.project_service = ProjectService(api_endpoint)
            self.testcase_service = TestCaseService(api_endpoint)
            self.task_service = TaskService(api_endpoint)
            self.viewpoints_service = ViewpointsService(api_endpoint)
            self.templates_service = TemplateService(api_endpoint)
            self.sync_service = SyncService(api_endpoint)
        else:
            logger.info("Using local storage mode only")
            self.auth_service = None
            self.project_service = None
            self.testcase_service = None
            self.task_service = None
            self.viewpoints_service = None
            self.templates_service = None
            self.sync_service = None

        # Check if we have a valid session token from previous login
        if session_manager.is_authenticated():
            self.current_user_token = session_manager.get_access_token()
            user_info = session_manager.get_user_info()
            if user_info and "username" in user_info:
                self._get_local_user(user_info["username"])
            logger.info("Restored session token for authenticated user")

    def _create_tables(self):
        """Create necessary tables in the SQLite if they do not exist."""
        try:
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL
                    );
                """
            )
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS projects (
                        uuid TEXT PRIMARY KEY,
                        user_id INTEGER,
                        name TEXT NOT NULL,
                        url TEXT,
                        description TEXT,
                        login_id TEXT,
                        password TEXT,
                        testcase_specification TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        created_by TEXT,
                        testcase_generated INTEGER DEFAULT 0,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    );
                """
            )
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS tasks (
                        uuid TEXT PRIMARY KEY,
                        project_id TEXT,
                        task_name TEXT NOT NULL,
                        url_test TEXT,
                        viewpoint_id TEXT,
                        request_login INTEGER,
                        specs_json TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        created_by TEXT,
                        celery_task_id TEXT,
                        generation_started_at TEXT,
                        generation_status TEXT,
                        include_component_viewpoints INTEGER DEFAULT 0,
                        generation_completed_at TEXT,
                        generation_error TEXT,
                        testcases_generated INTEGER DEFAULT 0,
                        status TEXT,
                        FOREIGN KEY (project_id) REFERENCES projects (uuid)
                    );
                """
            )
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS viewpoints (
                        uuid TEXT PRIMARY KEY,
                        project_id TEXT,
                        name TEXT NOT NULL,
                        viewpoint_type TEXT,
                        description TEXT,
                        details_json TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        created_by TEXT,
                        FOREIGN KEY (project_id) REFERENCES projects (uuid)
                    );
                """
            )
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS testcases(
                        uuid TEXT PRIMARY KEY,
                        task_uuid TEXT,
                        project_id TEXT,
                        test_field TEXT,
                        test_type TEXT,
                        test_case TEXT,
                        test_reference TEXT,
                        test_expect TEXT,
                        test_status TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        last_run_status TEXT,
                        last_run_time TEXT,
                        test_result_details TEXT,
                        checkpoint_data TEXT,
                        step_number INTEGER DEFAULT 0,
                        FOREIGN KEY (task_uuid) REFERENCES tasks (uuid)
                    )
                """
            )
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS sync_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation_type TEXT NOT NULL,
                        table_name TEXT NOT NULL,
                        record_uuid TEXT NOT NULL,
                        payload TEXT,
                        timestamp TEXT NOT NULL,
                        sync_status TEXT NOT NULL DEFAULT 'pending'
                    )"""
            )
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS sync_settings (
                        user_id INTEGER PRIMARY KEY,
                        enabled INTEGER DEFAULT 0,
                        auto_sync INTEGER DEFAULT 0,
                        interval_sync INTEGER DEFAULT 0,
                        interval_ms INTEGER DEFAULT 300000,
                        updated_at TEXT,
                        last_pull_at TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    );
                """
            )
            self.cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS viewpoints_templates (
                        uuid TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        viewpoint_type TEXT,
                        viewpoint_details TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    );
                """
            )
            self.conn.commit()
            logger.info("Database tables ensured.")
        except sqlite3.Error as e:
            logger.error("Error creating database tables: %s", e, exc_info=True)

    def _log_sync_operation(
        self,
        operation_type: str,
        table_name: str,
        record_uuid: str,
        payload: Optional[Dict] = None,
    ):
        "log a sync operation to the sync_log table."
        try:
            payload_json = json.dumps(payload) if payload else None
            timestamp = datetime.datetime.utcnow().isoformat()
            self.cursor.execute(
                """
                    INSERT INTO sync_log (operation_type, table_name, record_uuid, payload, timestamp)
                    values (?, ?, ?, ?, ?)
                """,
                (operation_type, table_name, record_uuid, payload_json, timestamp),
            )

            self.signals.sync_needed.emit()

            logger.info("Sync operation logged successfully.")
        except sqlite3.Error as e:
            logger.error("Error logging sync operation: %s", e, exc_info=True)
    
    def _compact_logs(self, pending_logs: List[Dict]) -> List[Dict]:
        compacted = {}
        for log in pending_logs:
            try:
                payload = json.loads(log["payload"]) if log["payload"] else {}
            except:
                payload = {}
        
            key = (log["table_name"], log["record_uuid"])
            op_type = log["operation_type"]

            if key not in compacted:
                compacted[key] = {
                    "operation_type": op_type,
                    "table_name": log["table_name"],
                    "record_uuid": log["record_uuid"],
                    "payload": payload,
                    "timestamp": log["timestamp"],
                    "log_ids": [log["id"]]
                }
                continue

            existing = compacted[key]
            existing["log_ids"].append(log["id"])

            if existing["operation_type"] == "CREATE":
                if op_type == "UPDATE":
                    existing["payload"].update(payload)
                    existing["timestamp"] = log["timestamp"]
                elif op_type == "DELETE":
                    del compacted[key]
            
            elif existing["operation_type"] == "UPDATE":
                if op_type == "UPDATE":
                    existing["payload"].update(payload)
                    existing["timestamp"] = log["timestamp"]
                elif op_type == "DELETE":
                    existing["operation_type"] = "DELETE"
                    existing["payload"] = None
            
            elif existing["operation_type"] == "DELETE":
                if op_type == "CREATE":
                    existing["operation_type"] = "UPDATE"
                    existing["payload"] = payload
        return list(compacted.values())

    def _sanitize_payload(self, payload: Dict) -> Dict:
        if not payload:
            return
        clean_data = payload.copy()
        filds_to_removes = ["id", "created_by", "user_id", "_id"]
        for field in filds_to_removes:
            clean_data.pop(field, None)
        return clean_data
    
    async def push_local_changes(self) -> bool:
        if not self.use_api or not self.current_user_token:
            return False
        try:
            self.cursor.execute(
                "SELECT * FROM sync_log WHERE sync_status = 'pending' ORDER BY id ASC"
            )
            rows = self.cursor.fetchall()
            if not rows:
                return True
            
            pending_logs = [dict(row) for row in rows]
            logger.info(f"Sync: Found {len(pending_logs)} pending logs. Compacting...")
            
            final_batch = self._compact_logs(pending_logs)
            all_processed_ids = [r["id"] for r in pending_logs]

            if not final_batch:
                logger.info("Sync: Logs compacted to empty (e.g. Create then Delete). Marking done.")
                self._delete_processed_logs(all_processed_ids)
                return True
            
            api_payload = []
            for item in final_batch:
                clean_item = item.copy()
                clean_item.pop("log_ids", None)
                if clean_item.get("payload"):
                    clean_item["payload"] = self._sanitize_payload(
                        clean_item["payload"]
                    )
                api_payload.append(clean_item)

            response, status_code = await self.sync_service.push_sync_data(
                self.current_user_token, api_payload
            )
            if status_code in [200, 202]:
                logger.info(f"Sync: Push successful. Deleting {len(all_processed_ids)} logs from local DB.")
                self._delete_processed_logs(all_processed_ids)
                return True
            else:
                logger.error(f"Sync: Push failed with status {status_code}")
                return False
        except Exception as e:
            logger.error("Sync push failed", exc_info=True)
            return False
    
    async def pull_remote_data(self) -> bool:
        """Optimized Incremental Pull using Delta-sync and Batch Upsert."""
        if not self.use_api or not self.current_user_token or not self.current_local_user_id:
            return False
        try:
            self.cursor.execute("SELECT last_pull_at FROM sync_settings WHERE user_id = ?", (self.current_local_user_id,))
            row = self.cursor.fetchone()
            since_timestamp = row["last_pull_at"] if row and row["last_pull_at"] else "1970-01-01T00:00:00Z"
            
            response, status = await self.sync_service.pull_sync_data(self.current_user_token, since_timestamp)
            if status != 200:
                logger.error(f"Sync pull failed with status {status}")
                return False
            
            self.conn.execute("BEGIN TRANSACTION")
            try:
                if response.get("projects"):
                    project_data = [
                        (p["uuid"], self.current_local_user_id, p["name"], p["url"], p["description"], 
                         p.get("login_id"), p.get("password"), json.dumps(p.get("testcase_specification", [])),
                         p["created_at"], p["updated_at"], p.get("created_by"))
                        for p in response["projects"]
                    ]
                    self.cursor.executemany(
                        """
                            INSERT OR REPLACE INTO projects (uuid, user_id, name, url, description, login_id, password, testcase_specification, created_at, updated_at, created_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        project_data
                    )

                if response.get("tasks"):
                    task_data = [
                        (t["uuid"], t["project_id"], t["task_name"], t.get("url_test"), t.get("viewpoint_id"),
                         t.get("request_login", 0), json.dumps(t.get("specs_json", [])), t["created_at"], t["updated_at"],
                         t.get("created_by"), t.get("generation_status"), t.get("status"))
                        for t in response["tasks"]
                    ]
                    self.cursor.executemany(
                        """
                            INSERT OR REPLACE INTO tasks (uuid, project_id, task_name, url_test, viewpoint_id, 
                            request_login, specs_json, created_at, updated_at, created_by, generation_status, status) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                    task_data
                )
                
                if response.get("viewpoints"):
                    vp_data = [
                        (v["uuid"], v["project_id"], v["name"], v.get("viewpoint_type"), 
                         json.dumps(v.get("viewpoint_details", [])), v["created_at"], v["updated_at"])
                        for v in response["viewpoints"]
                    ]
                    self.cursor.executemany(
                        """
                            INSERT OR REPLACE INTO viewpoints (uuid, project_id, name, viewpoint_type, details_json, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                    vp_data
                )
                
                if response.get("testcases"):
                    tc_data = [
                        (tc["uuid"], tc.get("task_uuid"), tc.get("project_id"), tc.get("test_field"), 
                         tc.get("test_type"), tc.get("test_case"), tc.get("test_status"), 
                         json.dumps(tc.get("test_result_details", [])), tc["created_at"], tc["updated_at"])
                        for tc in response["testcases"]
                    ]
                    self.cursor.executemany(
                        """INSERT OR REPLACE INTO testcases (uuid, task_uuid, project_id, test_field, test_type, 
                           test_case, test_status, test_result_details, created_at, updated_at) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        tc_data
                    )
                
                new_timestamp = response.get("new_timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
                self.cursor.execute(
                    "UPDATE sync_settings SET last_pull_at = ? WHERE user_id = ?",
                    (new_timestamp, self.current_local_user_id)
                )
                self.save()
                return True
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Sync pull transaction failed: {e}")
                return False

        except Exception as e:
            logger.error("Sync pull failed", exc_info=True)
            return False
    
    async def save_sync_config(self, config_data: dict):
        if not self.current_local_user_id:
            logger.error("Cannot save sync config: No authenticated local user.")
            return False
        
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            self.cursor.execute(
                """
                    INSERT OR REPLACE INTO sync_settings 
                    (user_id, enabled, auto_sync, interval_sync, interval_ms, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.current_local_user_id,
                    config_data.get("enabled", 0),
                    config_data.get("auto_sync", 0),
                    config_data.get("interval_sync", 0),
                    config_data.get("interval_ms", 300000),
                    now
                )
            )
            self.save()
            logger.info("Sync configuration saved successfully for user_id %s", self.current_local_user_id)
        except sqlite3.Error as e:
            logger.error("Failed to save sync configuration: %s", e, exc_info=True)

    async def get_sync_config(self) -> dict:
        if not self.current_local_user_id:
            logger.error("Cannot get sync config: No authenticated local user.")
            return {}
        try:
            self.cursor.execute(
                "SELECT * FROM sync_settings WHERE user_id = ?", 
                (self.current_local_user_id,)
            )
            row = self.cursor.fetchone()
            if row:
                return {
                    "enabled": bool(row["enabled"]),
                    "auto_sync": bool(row["auto_sync"]),
                    "interval_sync": bool(row["interval_sync"]),
                    "interval_ms": row["interval_ms"],
                }
        except sqlite3.Error as e:
            logger.error("Failed to retrieve sync configuration: %s", e, exc_info=True)
            return {}
        return {}

    def _delete_processed_logs(self, log_ids: List[int]):
        """Permanently delete processed log lines"""
        if not log_ids: return
        try:
            placeholders = ",".join("?" * len(log_ids))
            self.cursor.execute(
                f"DELETE FROM sync_log WHERE id IN ({placeholders})",
                tuple(log_ids)
            )
            self.save() 
            logger.debug(f"Cleaned up {len(log_ids)} records from sync_log.")
        except sqlite3.Error as e:
            logger.error("Failed to delete processed sync logs", exc_info=True)

    def has_pending_logs(self) -> bool:
        try:
            self.cursor.execute(
                "SELECT 1 FROM sync_log WHERE sync_status = 'pending' LIMIT 1"
            )
            return self.cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking pending logs: {e}")
            return False
        
    def get_current_user(self) -> Optional[User]:
        """Returns the current User object based on current_local_user_id."""
        if self.current_local_user_id:
            return self.get_user_by_id(self.current_local_user_id)
        return None

    def _get_local_user(self, username: str) -> Optional[User]:
        """Retrieve a user from the local database by username."""
        try:
            self.cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user_row = self.cursor.fetchone()
            if user_row:
                self.current_local_user_id = user_row["id"]
                return self.current_local_user_id
            else:
                self.cursor.execute(
                    "INSERT INTO users (username) VALUES (?)", (username,)
                )
                self.conn.commit()
                self.current_local_user_id = self.cursor.lastrowid
                return self.current_local_user_id
        except sqlite3.Error as e:
            logger.error("Error retrieving/inserting local user: %s", e, exc_info=True)
            return None

    def load(self):
        """Loads the database from the JSON file and reconstructs the object graph."""
        pass

    def save(self):
        """Serializes the current state of all objects to the JSON file."""
        try:
            self.conn.commit()
            logger.info("Database changes committed successfully.")
        except sqlite3.Error as e:
            logger.error("Error saving database changes: %s", e, exc_info=True)

    # --- Authentication Methods ---

    async def auto_login(self, username: str, password: str) -> bool:
        """
        Đăng nhập thẳng vào server bằng tài khoản demo (không có màn hình login).
        Tài khoản chưa tồn tại trên server thì tự đăng ký rồi đăng nhập lại.
        """
        if await self.authenticate_user(username, password):
            return True
        logger.info("Demo user '%s' not found on server, registering", username)
        if not await self.register_user(username, password):
            return False
        return await self.authenticate_user(username, password)

    async def authenticate_user(self, username: str, password: str) -> bool:
        """
        Authenticate user using API or local storage.
        Returns True if authentication successful, False otherwise.
        """
        logger.debug("Attempting to authenticate user: %s", username)
        if self.use_api and self.auth_service:
            try:
                response = await self.auth_service.login(username, password)
                logger.debug(
                    "API authentication response received for user: %s", response
                )
                if response and "access_token" in response:
                    token = response["access_token"]
                    self.current_user_token = token

                    # Save session for future use
                    response["username"] = username
                    session_manager.set_access_token(token, response)
                    
                    self._get_local_user(username)

                    user_obj = self.get_current_user()
                    self.signals.current_user_changed.emit(user_obj)

                    return True
                elif response and "token" in response:
                    self.current_user_token = response["token"]
                    # Save session for future use
                    response["username"] = username  # Ensure username is included
                    session_manager.set_access_token(response["token"], response)
                    logger.info("Successfully authenticated user via API: %s", username)
                    return True
                else:
                    logger.warning(
                        "API authentication failed for user %s: No valid token",
                        username,
                    )
            except Exception:
                logger.error(
                    "API authentication failed for user %s", username, exc_info=True
                )

        logger.warning("Authentication failed for user: %s", username)
        return False

    async def register_user(self, username: str, password: str) -> bool:
        """
        Register a new user using API or local storage.
        Returns True if registration successful, False otherwise.
        """
        logger.debug("Attempting to register user: %s", username)
        if not (self.use_api and self.auth_service):
            logger.error("Cannot register: API service is not configured.")
            return False

        if self.use_api and self.auth_service:
            try:
                response = await self.auth_service.register(username, password)
                if response:
                    logger.info("Successfully registered user via API: %s", username)
                    return True
            except Exception:
                logger.error(
                    "API registration failed for user %s", username, exc_info=True
                )
                return False

    async def logout_user(self):
        """Clear current user session and logout from API if needed."""
        if self.use_api and self.auth_service and self.current_user_token:
            try:
                logger.debug("Logging out user with token: %s", self.current_user_token)
                await self.auth_service.logout(self.current_user_token)
            except Exception:
                logger.error("API logout failed", exc_info=True)
        logger.info("Clearing current user session")
        self.current_user_token = None
        self.current_local_user_id = None
        # Clear the session when logging out
        session_manager.logout()

        self.signals.current_user_changed.emit(None)

    # --- Public API for the rest of the app ---

    def commit(self):
        """Explicitly saves all changes to the database file. Alias for save()."""
        self.save()

    async def get_all_projects(self) -> List[Project]:
        """Get all projects from API or local storage."""
        logger.debug("Fetching all projects")
        try:
            # Cursor riêng: hàm này chạy ở luồng nền trong khi giao diện vẫn dùng self.cursor
            cur = self.conn.cursor()
            cur.execute(
                "SELECT * FROM projects WHERE user_id = ?",
                (self.current_local_user_id,),
            )
            project_rows = cur.fetchall()
            projects = []
            for row in project_rows:
                project_dict = dict(row)
                # Kèm task + testcase để các ô đếm Cases / OK / NG hiển thị đúng
                project_dict["tasks"] = await self.list_tasks(project_dict["uuid"])
                projects.append(Project.from_dict(project_dict))
            self.projects = projects
            self._projects_by_id = {p.project_id: p for p in self.projects}
            return self.projects
        except sqlite3.Error as e:
            logger.error("Failed to get projects from SQLite: %s", e, exc_info=True)
            return []

    def get_all_projects_sync(self) -> List[Project]:
        """Synchronous wrapper for get_all_projects."""
        logger.debug("Synchronous call to get_all_projects")
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.get_all_projects())
                return result
            finally:
                loop.close()
        except Exception:
            logger.error("Sync get_all_projects failed", exc_info=True)
            return self.projects

    async def get_project_by_id(
        self, project_id: str, user_id: Optional[int] = None
    ) -> Optional[Project]:  # Changed to str
        """Retrieves a single project by its unique ID from API or local storage."""
        if not project_id:
            return None

        target_user_id = user_id if user_id is not None else self.current_local_user_id

        logger.debug("Fetching project by ID: %s", project_id)
        try:
            self.cursor.execute(
                "SELECT * FROM projects WHERE uuid = ? AND user_id = ?",
                (str(project_id), target_user_id),
            )
            row = self.cursor.fetchone()
            if row:
                return Project.from_dict(dict(row))
        except sqlite3.Error as e:
            logger.error(
                "Failed to get project by ID from SQLite: %s", e, exc_info=True
            )
        return None

    def get_project_by_id_sync(
        self, project_id: str, user_id: Optional[int] = None
    ) -> Optional[Project]:  # Changed to str
        """Synchronous wrapper for get_project_by_id."""
        if not project_id:
            return None

        logger.debug(
            "Synchronous call to get_project_by_id for project: %s", project_id
        )
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.get_project_by_id(project_id, user_id)
                )
                return result
            finally:
                loop.close()
        except Exception:
            logger.error(
                "Sync get_project_by_id failed for project %s",
                project_id,
                exc_info=True,
            )
            return self._projects_by_id.get(str(project_id))  # Convert to str

    async def add_project(
        self,
        name: str,
        url: str = "",
        description: str = "",
        login_id: str = "",
        password: str = "",  # nosec B107 # Optional password param
    ) -> Optional[Project]:
        """Creates a new project via API or local storage and returns the new object."""
        if not self.current_local_user_id:
            logger.error("Cannot add project: No authenticated local user.")
            return None

        new_uuid = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)
        project = Project(
            project_id=new_uuid,
            name=name,
            url=url,
            description=description,
            login_id=login_id,
            password=password,
            created_at=now,
            updated_at=now,
            testcase_generated=False,
        )
        try:
            self.cursor.execute(
                """
                INSERT INTO projects (uuid, user_id, name, url, description, login_id, password, created_at, updated_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ? , ?)
                """,
                (
                    project.project_id,
                    self.current_local_user_id,
                    project.name,
                    project.url,
                    project.description,
                    project.login_id,
                    project.password,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                    self.current_local_user_id,
                ),
            )

            self._log_sync_operation(
                "CREATE", "projects", project.project_id, project.to_dict()
            )
            self.save()
            logger.info("Project added successfully: %s", project.name)
            return project, 201
        except sqlite3.Error as e:
            logger.error("Failed to add project to SQLite: %s", e, exc_info=True)
            return None

    def add_project_sync(
        self,
        name: str,
        url: str = "",
        description: str = "",
        login_id: str = "",
        password: str = "",  # nosec B107 # Optional password param
    ) -> Optional[Project]:
        """Synchronous wrapper for add_project."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.add_project(name, url, description, login_id, password)
                )
                return result
            finally:
                loop.close()
        except Exception:
            logger.error("Sync add_project failed", exc_info=True)
            return None

    async def delete_project(self, project_id: str) -> bool:  # Changed to str
        """Deletes a project by its ID via API or local storage."""
        is_deleting_current_project = self.current_project and str(
            self.current_project.project_id
        ) == str(project_id)
        try:
            self.cursor.execute(
                "DELETE FROM projects WHERE uuid = ? AND user_id = ?",
                (str(project_id), self.current_local_user_id),
            )

            if self.cursor.rowcount > 0:
                self._log_sync_operation("DELETE", "projects", str(project_id))
                if is_deleting_current_project:
                    project_name = self.current_project.name
                    logger.info("Deleted current project: %s", project_name)
                    self.current_project = None
                    self.signals.current_project_changed.emit(None)
                self.save()
                return True
        except sqlite3.Error as e:
            logger.error("Failed to delete project from SQLite: %s", e, exc_info=True)
        return False

    def delete_project_sync(self, project_id: str) -> bool:  # Changed to str
        """Synchronous wrapper for delete_project."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.delete_project(project_id))
                return bool(result)
            finally:
                loop.close()
        except Exception:
            logger.error("Sync delete_project failed", exc_info=True)
            return False

    async def patch_update_project(self, project_to_update: Project) -> bool:
        """Updates an existing project's data via API or local storage."""
        try:
            self.cursor.execute(
                """
                    UPDATE projects
                    SET name = ?, url = ?, description = ?, login_id = ?, password = ?, updated_at = ?
                    WHERE uuid = ? AND user_id = ?
                """,
                (
                    project_to_update.name,
                    project_to_update.url,
                    project_to_update.description,
                    project_to_update.login_id,
                    project_to_update.password,
                    project_to_update.updated_at.isoformat(),
                    str(project_to_update.project_id),
                    self.current_local_user_id,
                ),
            )
            if self.cursor.rowcount > 0:
                self._log_sync_operation(
                    "UPDATE",
                    "projects",
                    str(project_to_update.project_id),
                    project_to_update.to_dict(),
                )
                self.save()
                logger.info("Successfully updated project: %s", project_to_update.name)
                return True
        except sqlite3.Error as e:
            logger.error("Failed to update project in SQLite: %s", e, exc_info=True)
        return False

    def update_project_sync(self, project_to_update: Project) -> bool:
        """Synchronous wrapper for update_project."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.patch_update_project(project_to_update)
                )
                return result
            finally:
                loop.close()
        except Exception:
            logger.error("Sync update_project failed", exc_info=True)
            return False

    def update_project_specifications_sync(
        self, project_id: str, specifications: List[Dict]
    ) -> bool:
        """Synchronous wrapper for update_project_specifications_async."""
        return asyncio.run(
            self.update_project_specifications(project_id, specifications)
        )

    async def update_project_specifications(
        self, project_id: str, specifications: List[Dict]
    ) -> bool:
        """Asynchronously updates a project's test case specifications."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            spec_json = json.dumps(specifications)
            self.cursor.execute(
                """
                    UPDATE projects
                    SET testcase_specification = ?, updated_at = ?
                    WHERE uuid = ? AND user_id = ?
                """,
                (spec_json, now, project_id, self.current_local_user_id),
            )
            if self.cursor.rowcount > 0:
                update_data = {"testcase_specification": specifications}
                self._log_sync_operation("UPDATE", "projects", project_id, update_data)
                self.save()
                self.signals.project_edited.emit()
                return True
        except sqlite3.Error as e:
            logger.error(
                "Failed to update project specifications in SQLite: %s",
                e,
                exc_info=True,
            )
        return False

    def get_current_project(self) -> Optional[Project]:
        """
        Returns the currently selected Project object.
        Returns None if no project is selected.
        """
        return self.current_project

    async def set_current_project(self, project_id: str):  # Changed to str
        """Sets the current project by looking it up by its ID."""
        # Avoid redundant API calls and signal emissions if already set
        if self.current_project and str(self.current_project.project_id) == str(
            project_id
        ):
            logger.debug("Project %s is already the current project.", project_id)
            return

        self.current_project = await self.get_project_by_id(
            project_id, self.current_local_user_id
        )
        if self.current_project:
            logger.info("Current project set to: %s", self.current_project.name)
        else:
            logger.warning("No project found with ID: %s", project_id)

        self.signals.current_project_changed.emit(self.current_project)

    def set_current_project_sync(self, project_id: str):  # Changed to str
        """Synchronous wrapper for set_current_project."""
        logger.debug("Setting current project synchronously: %s", project_id)
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.set_current_project(project_id))
            finally:
                loop.close()
        except Exception:
            logger.error(
                "Sync set_current_project failed for project %s",
                project_id,
                exc_info=True,
            )
            # Fallback: try to get from local cache
            self.current_project = self._projects_by_id.get(
                str(project_id)
            )  # Convert to str

    async def get_user_info(self) -> Optional[Dict]:
        """Get current user information from API."""
        if self.use_api and self.auth_service and self.current_user_token:
            try:
                response = await self.auth_service.get_user_info(
                    self.current_user_token
                )
                return response
            except Exception:
                logger.error("API get_user_info failed", exc_info=True)
        elif not self.use_api and self.current_local_user_id:
            user = self.get_user_by_id(self.current_local_user_id)
            if user:
                return {"id": user.id, "username": user.username}
        return None

    def get_user_info_sync(self) -> Optional[Dict]:
        """Synchronous wrapper for get_user_info."""
        # First check if we have user info in the session manager
        user_info = session_manager.get_user_info()
        if user_info:
            return user_info

        if not self.use_api or not self.current_user_token:
            if self.current_local_user_id:
                user = self.get_user_by_id(self.current_local_user_id)
                if user:
                    return {"id": user.id, "username": user.username}
            return None

        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.get_user_info())
                return result
            finally:
                loop.close()
        except Exception:
            logger.error("Sync get_user_info failed", exc_info=True)
            return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Finds a user by their username."""
        try:
            self.cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            user_data = self.cursor.fetchone()
            if user_data:
                return User.from_dict(dict(user_data))
            return None
        except sqlite3.Error as e:
            logger.error(
                "Failed to get user by username from SQLite: %s", e, exc_info=True
            )
            return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Finds a user by their ID."""
        try:
            self.cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            user_data = self.cursor.fetchone()
            if user_data:
                return User.from_dict(dict(user_data))
            return None
        except sqlite3.Error as e:
            logger.error("Failed to get user by ID from SQLite: %s", e, exc_info=True)
            return None

    # --- TestCase Management ---

    async def create_test_case(self, test_case_data: Dict) -> Optional[Dict]:
        """Create a new test case via API."""
        logger.debug("Creating test case with data: %s", test_case_data)

        new_uuid = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        test_case_data["uuid"] = new_uuid
        test_case_data["created_at"] = now
        test_case_data["updated_at"] = now
        test_case_data["test_status"] = "not_started"

        task_uuid = test_case_data.get("task_uuid")
        if not task_uuid:
            task_uuid = test_case_data.get("task_id")

        if not task_uuid and self.current_task:
            task_uuid = self.current_task.task_id

        test_case_data["task_uuid"] = str(task_uuid) if task_uuid else ""
        test_case_data["task_id"] = test_case_data["task_uuid"]

        if "project_id" in test_case_data:
            test_case_data["project_id"] = str(test_case_data["project_id"])
        elif self.current_project:
            test_case_data["project_id"] = str(self.current_project.project_id)
        else:
            test_case_data["project_id"] = ""

        details_json = "[]"
        if "test_result_details" in test_case_data:
            details_json = json.dumps(test_case_data["test_result_details"])

        try:
            self.cursor.execute(
                """
                    INSERT INTO testcases (
                        uuid, task_uuid, project_id, test_field, test_type, 
                        test_case, test_reference, test_expect, test_status, 
                        created_at, updated_at, test_result_details, last_run_status, step_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_uuid,
                    test_case_data.get("task_uuid", ""),
                    test_case_data.get("project_id", ""),
                    test_case_data.get("test_field", ""),
                    test_case_data.get("test_type", ""),
                    test_case_data.get("test_case", ""),
                    test_case_data.get("test_reference", ""),
                    test_case_data.get("test_expect", ""),
                    test_case_data.get("test_status", "not_started"),
                    now,
                    now,
                    details_json,
                    test_case_data.get("last_run_status", "not_run"),
                    test_case_data.get("step_number", 0),
                ),
            )

            if self.cursor.rowcount > 0:
                self.save()
                self._log_sync_operation(
                    "CREATE", "testcases", new_uuid, test_case_data
                )

                test_case_data["id"] = new_uuid
                if "task_uuid" in test_case_data:
                    test_case_data["task_id"] = test_case_data["task_uuid"]

                logger.info("Test case created locally: %s", new_uuid)
                return test_case_data
        except sqlite3.Error as e:
            logger.error("Failed to create test case in SQLite: %s", e, exc_info=True)
        return None

    # --- Task Management ---

    async def list_tasks(self, project_id: str) -> List[Dict]:  # Changed to str
        """List tasks for a project via API."""
        logger.debug("Listing tasks for project: %s", project_id)
        tasks = []
        try:
            cur = self.conn.cursor()  # cursor riêng, an toàn khi gọi từ luồng nền
            cur.execute(
                "SELECT * FROM tasks WHERE project_id = ?", (project_id,)
            )
            rows = cur.fetchall()
            for row in rows:
                task_dict = dict(row)
                specs_json = task_dict.pop("specs_json", "[]")
                task_dict["items"] = json.loads(specs_json or "[]")
                cur.execute(
                    "SELECT uuid, test_status FROM testcases WHERE task_uuid = ?",
                    (task_dict["uuid"],),
                )
                task_dict["test_cases"] = [dict(tc) for tc in cur.fetchall()]
                tasks.append(task_dict)
            return tasks
        except sqlite3.Error as e:
            logger.error("Failed to list tasks from SQLite: %s", e, exc_info=True)
            return []

    async def create_task(
        self, task_data: Dict, project_id: str
    ) -> Optional[Dict]:  # Changed to str
        """Create a new task for a project via API."""
        logger.debug("Creating task for project %s: %s", project_id, task_data)
        if not self.current_local_user_id:
            logger.error("Cannot create task: No authenticated local user.")
            return None
        new_uuid = str(uuid.uuid4())
        task_data["uuid"] = new_uuid
        task_data["project_id"] = project_id
        specs_list = task_data.get("items", []) or task_data.get("specs", [])
        specs_json = json.dumps(specs_list)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        try:
            self.cursor.execute(
                """
                    INSERT INTO tasks (uuid, project_id, task_name, url_test, viewpoint_id, request_login, 
                    specs_json, created_at, updated_at, created_by, generation_started_at, 
                    generation_status, include_component_viewpoints)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_uuid,
                    project_id,
                    task_data.get("task_name", ""),
                    task_data.get("url_test", ""),
                    task_data.get("viewpoint_id", ""),
                    1 if task_data.get("request_login") else 0,
                    specs_json,
                    now,
                    now,
                    self.current_local_user_id,
                    now,
                    task_data.get("generation_status", "not_started"),
                    1 if task_data.get("include_component_viewpoints", True) else 0,
                ),
            )
            self._log_sync_operation("CREATE", "tasks", new_uuid, task_data)
            self.save()
            return task_data
        except sqlite3.Error as e:
            logger.error("Failed to create task in SQLite: %s", e, exc_info=True)
            return None

    async def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a specific task via API."""
        logger.debug("Fetching task: %s", task_id)
        try:
            self.cursor.execute("SELECT * FROM tasks WHERE uuid = ?", (task_id,))
            row = self.cursor.fetchone()
            if row:
                task_dict = dict(row)
                specs_json = task_dict.pop("specs_json", "[]")
                task_dict["items"] = json.loads(specs_json or "[]")
                return task_dict
        except sqlite3.Error as e:
            logger.error("Failed to get task from SQLite: %s", e, exc_info=True)
        return None

    async def update_task(self, task_id: str, task_data: Dict) -> bool:
        """Update a specific task via API."""
        logger.debug("Updating task %s: %s", task_id, task_data)

        valid_columns = {
            "task_name",
            "url_test",
            "viewpoint_id",
            "request_login",
            "specs_json",
            "generation_status",
            "generation_started_at",
            "celery_task_id",
            "include_component_viewpoints",
            "updated_at",
            "generation_completed_at",
            "generation_error",
            "testcases_generated",
            "status",
        }

        if "items" in task_data:
            task_data["specs_json"] = json.dumps(task_data["items"])

        if "request_login" in task_data:
            task_data["request_login"] = 1 if task_data["request_login"] else 0

        if "include_component_viewpoints" in task_data:
            task_data["include_component_viewpoints"] = (
                1 if task_data["include_component_viewpoints"] else 0
            )

        task_data["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()

        set_clauses = []
        params = []

        for key, value in task_data.items():
            if key in valid_columns:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        if not set_clauses:
            logger.warning("No valid columns to update for task %s", task_id)
            return False

        params.append(task_id)

        query = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE uuid = ?"

        try:
            self.cursor.execute(query, tuple(params))
            if self.cursor.rowcount > 0:
                self.conn.commit()
                self._log_sync_operation("UPDATE", "tasks", task_id, task_data)
                return True
            else:
                logger.warning(f"Task {task_id} not found or no changes made.")
        except sqlite3.Error as e:
            logger.error("Failed to update task in SQLite: %s", e, exc_info=True)

        return False

    async def delete_task(self, task_id: str) -> bool:
        """Delete a specific task via API."""
        logger.debug("Deleting task %s", task_id)
        try:
            self.cursor.execute("DELETE FROM tasks WHERE uuid = ?", (task_id,))
            if self.cursor.rowcount > 0:
                self._log_sync_operation("DELETE", "tasks", task_id)
                self.save()
                return True
        except sqlite3.Error as e:
            logger.error("Failed to delete task from SQLite: %s", e, exc_info=True)
        return False

    # Sync wrappers for tasks
    def list_tasks_sync(self, project_id: str) -> List[Dict]:  # Changed to str
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.list_tasks(project_id))
            finally:
                loop.close()
        except Exception:
            logger.error("Sync list_tasks failed", exc_info=True)
            return []

    def create_task_sync(
        self, task_data: Dict, project_id: str
    ) -> Optional[Dict]:  # Changed to str
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.create_task(task_data, project_id))
            finally:
                loop.close()
        except Exception:
            logger.error("Sync create_task failed", exc_info=True)
            return None

    def get_task_sync(self, task_id: str) -> Optional[Dict]:
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.get_task(task_id))
            finally:
                loop.close()
        except Exception:
            logger.error("Sync get_task failed", exc_info=True)
            return None

    def update_task_sync(self, task_id: str, task_data: Dict) -> bool:
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return bool(
                    loop.run_until_complete(self.update_task(task_id, task_data))
                )
            finally:
                loop.close()
        except Exception:
            logger.error("Sync update_task failed", exc_info=True)
            return False

    def delete_task_sync(self, task_id: str) -> bool:
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return bool(loop.run_until_complete(self.delete_task(task_id)))
            finally:
                loop.close()
        except Exception:
            logger.error("Sync delete_task failed", exc_info=True)
            return False

    def get_current_task(self) -> Optional[Task]:
        """Returns the currently selected task. This is a synchronous operation."""
        return self.current_task

    def set_current_task_sync(self, task_id: Optional[str]):
        """
        Sets the active task for subsequent operations. Pass None to clear.
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.set_current_task(task_id))
            finally:
                loop.close()
        except Exception:
            logger.error("Sync delete_task failed", exc_info=True)
            return False

    async def set_current_task(self, task_id: Optional[str]):
        """
        Asynchronously sets the active task. Pass None to clear the current task.
        """
        if not task_id:
            if self.current_task is not None:
                self.current_task = None
                logger.info("Current task cleared.")
                self.signals.current_task_changed.emit(None)
            return

        # Avoid redundant updates and signal emissions
        if self.current_task and self.current_task.task_id == task_id:
            return

        task_data = await self.get_task(task_id)
        if task_data:
            self.current_task = Task.from_dict(task_data)
        else:
            self.current_task = None

        if self.current_task:
            logger.info(
                "Current task set: %s (%s)",
                self.current_task.task_name,
                self.current_task.task_id,
            )
        else:
            logger.warning(
                "Failed to set current task: No task found with ID %s", task_id
            )

        self.signals.current_task_changed.emit(self.current_task)

    # --- Task Testcase Generation ---

    async def generate_testcases(
        self, task_id: str, options: Dict = None
    ) -> Optional[Dict]:
        """Generate testcases for a task via API."""
        logger.debug(
            "Generating testcases for task ID: %s with options: %s", task_id, options
        )

        if not (self.use_api and self.task_service and self.current_user_token):
            logger.error("API is not configured or user is not authenticated.")
            return None

        options = options or {}
        force_regenerate = options.get("force_regenerate", True)
        include_component_viewpoints = options.get(
            "include_component_viewpoints", False
        )

        task_data = await self.get_task(task_id)
        if not task_data:
            logger.error("Task not found for ID: %s", task_id)
            return None

        if int(task_data.get("created_by")) != self.current_local_user_id:
            logger.error("Unauthorized: Current user does not own task ID: %s", task_id)
            return None

        project_id = task_data.get("project_id")

        project_data = await self.get_project_by_id(
            project_id, self.current_local_user_id
        )
        if not project_data:
            logger.error("Project not found for ID: %s", project_id)
            return None

        if int(project_data.created_by) != self.current_local_user_id:
            logger.error(
                "Unauthorized: Current user does not own project ID: %s", project_id
            )
            return None

        project_details_dict = project_data.to_dict()
        keys_to_remove = ["user_id", "created_by"]
        for key in keys_to_remove:
            project_details_dict.pop(key, None)

        spec_json_str = project_details_dict.get("testcase_specification")
        if spec_json_str and isinstance(spec_json_str, str):
            try:
                project_details_dict["testcase_specification"] = json.loads(
                    spec_json_str
                )
            except json.JSONDecodeError:
                project_details_dict["testcase_specification"] = []

        main_viewpoint = await self.get_viewpoint(task_data.get("viewpoint_id", ""))
        if not main_viewpoint:
            logger.error(
                "Main viewpoint not found for ID: %s",
                task_data.get("viewpoint_id", ""),
            )
            return None

        viewpoint_details_dict = main_viewpoint.copy()
        keys_to_remove = ["project_id", "oid", "created_by", "description"]
        for key in keys_to_remove:
            viewpoint_details_dict.pop(key, None)

        component_viewpoints = {}
        if include_component_viewpoints:
            component_uuids = {
                (vt.get("uuid") if isinstance(vt, dict) else vt)
                for item in task_data.get("items", [])
                for vt in item.get("validation_types", [])
                if (vt.get("uuid") if isinstance(vt, dict) else vt)
            }
            if component_uuids:
                vp_tasks = [self.get_viewpoint(uuid) for uuid in component_uuids]
                results = await asyncio.gather(*vp_tasks, return_exceptions=True)
                for vp in results:
                    if vp and not isinstance(vp, Exception):
                        component_vp_dict = vp.copy()
                        keys_to_remove = [
                            "project_id",
                            "oid",
                            "created_by",
                            "description",
                        ]
                        for key in keys_to_remove:
                            component_vp_dict.pop(key, None)

                        component_viewpoints[vp["uuid"]] = component_vp_dict

        payload = {
            "url_test": task_data.get("url_test", ""),
            "task_name": task_data.get("task_name", ""),
            "viewpoint_data": viewpoint_details_dict,
            "project_details": project_details_dict,
            "request_login": bool(task_data.get("request_login")),
            "items": task_data.get("items", []),
            "uuid": task_id,
            "updated_at": task_data.get("updated_at"),
            "celery_task_id": task_data.get("celery_task_id"),
            "generation_started_at": task_data.get("generation_started_at"),
            "generation_status": task_data.get("generation_status"),
            "include_component_viewpoints": include_component_viewpoints,
            "force_regenerate": force_regenerate,
            "component_viewpoints": component_viewpoints,
        }

        return await self.task_service.generate_testcases(
            self.current_user_token, task_id, payload
        )

    async def get_generation_status(self, task_id: str) -> Optional[Dict]:
        """Get testcase generation status for a task via API."""
        logger.debug("Getting generation status for task ID: %s", task_id)
        if (
            self.use_api
            and getattr(self, "task_service", None)
            and self.current_user_token
        ):
            try:
                response = await self.task_service.get_generation_status(
                    self.current_user_token, task_id
                )

                if response and response.get("generation_status") == "completed":
                    generated_testcases = response.get("generated_testcases", [])
                    if generated_testcases:
                        logger.info(
                            f"[DEBUG DATA FLOW] Attempting to save {len(generated_testcases)} testcases locally..."
                        )
                        self.save_generated_testcases_locally(
                            task_id, generated_testcases
                        )
                    else:
                        logger.warning(
                            f"[DEBUG DATA FLOW] No testcases found in response to save for Task {task_id}"
                        )

                task_update_data = {}
                fields_to_update = [
                    "generation_status",
                    "celery_task_id",
                    "generation_error",
                    "testcases_generated",
                    "status",
                ]

                for field in fields_to_update:
                    if field in response:
                        task_update_data[field] = response[field]

                if "generation_started_at" in response:
                    start_at = response["generation_started_at"]
                    if isinstance(start_at, datetime.datetime):
                        task_update_data["generation_started_at"] = start_at.isoformat()
                    else:
                        task_update_data["generation_started_at"] = str(start_at)

                if "generation_completed_at" in response:
                    completed_at = response["generation_completed_at"]
                    task_update_data["generation_completed_at"] = (
                        completed_at.isoformat()
                        if isinstance(completed_at, datetime.datetime)
                        else str(completed_at)
                    )

                if task_update_data:
                    await self.update_task(task_id, task_update_data)

                return response
            except Exception:
                logger.error("API get_generation_status failed", exc_info=True)
        return None

    def save_generated_testcases_locally(self, task_uuid: str, testcases: List[Dict]):
        """Save generated testcases from server to local SQLite"""
        if not testcases:
            return False

        try:
            logger.info(
                f"[DEBUG DATA FLOW] Starting local save transaction for Task {task_uuid}"
            )

            self.cursor.execute(
                "SELECT project_id FROM tasks WHERE uuid = ?", (task_uuid,)
            )
            task_row = self.cursor.fetchone()

            local_project_id = None
            if task_row:
                local_project_id = task_row["project_id"]
                logger.debug(
                    f"Found local project_id {local_project_id} for task {task_uuid}"
                )
            else:
                logger.warning(f"CRITICAL: Task {task_uuid} not found in local DB!")

            self.cursor.execute(
                "DELETE FROM testcases WHERE task_uuid = ?", (task_uuid,)
            )

            for tc in testcases:
                created_at = tc.get("created_at")
                if isinstance(created_at, str):
                    created_at_str = created_at
                else:
                    created_at_str = datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()

                raw_pid = tc.get("project_id")
                final_pid = None

                if isinstance(raw_pid, dict) and "$oid" in raw_pid:
                    final_pid = raw_pid["$oid"]
                elif isinstance(raw_pid, str) and raw_pid:
                    final_pid = raw_pid

                if not final_pid:
                    final_pid = local_project_id

                self.cursor.execute(
                    """
                        INSERT OR REPLACE INTO testcases (
                            uuid, task_uuid, project_id, test_field, test_type, 
                            test_case, test_reference, test_expect, test_status, 
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tc.get("uuid", str(uuid.uuid4())),
                        task_uuid,
                        final_pid,
                        tc.get("test_field", ""),
                        tc.get("test_type", ""),
                        tc.get("test_case", ""),
                        tc.get("test_reference", ""),
                        tc.get("test_expect", ""),
                        "not_started",
                        created_at_str,
                        created_at_str,
                    ),
                )
            self.save()
            logger.info(
                f"Saved {len(testcases)} testcases to local SQLite for task {task_uuid}"
            )
            return True
        except sqlite3.Error as e:
            logger.error(
                "Failed to save generated testcases to SQLite: %s", e, exc_info=True
            )
            return False

    async def get_background_task_status(self, celery_task_id: str) -> Optional[Dict]:
        """Get background task status from Celery via API."""
        logger.debug("Getting background task status for ID: %s", celery_task_id)
        if (
            self.use_api
            and getattr(self, "task_service", None)
            and self.current_user_token
        ):
            try:
                response = await self.task_service.get_background_task_status(
                    self.current_user_token, celery_task_id
                )
                logger.debug("Background task status response: %s", response)
                return response
            except Exception:
                logger.error("API get_background_task_status failed", exc_info=True)
        return None

    # Sync wrappers for testcase generation
    def generate_testcases_sync(
        self, task_id: str, options: Dict = None
    ) -> Optional[Dict]:
        """Synchronous wrapper for generate_testcases."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.generate_testcases(task_id, options)
                )
            finally:
                loop.close()
        except Exception:
            logger.error("Sync generate_testcases failed", exc_info=True)
            return None

    def get_generation_status_sync(self, task_id: str) -> Optional[Dict]:
        """Synchronous wrapper for get_generation_status."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.get_generation_status(task_id))
            finally:
                loop.close()
        except Exception:
            logger.error("Sync get_generation_status failed", exc_info=True)
            return None

    def get_background_task_status_sync(self, celery_task_id: str) -> Optional[Dict]:
        """Synchronous wrapper for get_background_task_status."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.get_background_task_status(celery_task_id)
                )
            finally:
                loop.close()
        except Exception:
            logger.error("Sync get_background_task_status failed", exc_info=True)
            return None

    # --- TestCase Management ---

    async def get_test_cases(
        self, project_id: str, task_id: Optional[str] = None
    ) -> Optional[List[Dict]]:  # Changed to str
        """Get test cases for a project via API."""
        try:
            self.cursor.execute(
                "SELECT * FROM testcases WHERE project_id = ? AND task_uuid = ?",
                (str(project_id), str(task_id)),
            )

            rows = self.cursor.fetchall()
            results = []

            for row in rows:
                row_dict = dict(row)
                if "test_result_details" in row_dict and isinstance(
                    row_dict["test_result_details"], str
                ):
                    try:
                        if row_dict["test_result_details"]:
                            row_dict["test_result_details"] = json.loads(
                                row_dict["test_result_details"]
                            )
                        else:
                            row_dict["test_result_details"] = []
                    except json.JSONDecodeError:
                        row_dict["test_result_details"] = []

                results.append(row_dict)

            logger.debug(f"Loaded {len(results)} testcases from local DB.")
            return results

        except sqlite3.Error as e:
            logger.error("Failed to get test cases from SQLite: %s", e, exc_info=True)
            return []

    async def update_test_case(
        self, test_case_id: str, test_case_data: Dict
    ) -> bool:  # Changed to str
        """Update a test case via API."""
        logger.debug("Updating test case with ID: %s", test_case_id)

        valid_columns = {
            "test_field",
            "test_type",
            "test_case",
            "test_reference",
            "test_expect",
            "test_status",
            "last_run_status",
            "last_run_time",
            "test_result_details",
            "updated_at",
            # "test_result",
            "checkpoint_data",
            "step_number",
        }

        if "test_result_details" in test_case_data:
            if isinstance(test_case_data["test_result_details"], (list, dict)):
                test_case_data["test_result_details"] = json.dumps(
                    test_case_data["test_result_details"]
                )
        
        if "checkpoint_data" in test_case_data:
            if isinstance(test_case_data["checkpoint_data"], (list, dict)):
                test_case_data["checkpoint_data"] = json.dumps(
                    test_case_data["checkpoint_data"],
                    ensure_ascii=False
                )

        test_case_data["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()

        set_clauses = []
        params = []

        for key, value in test_case_data.items():
            if key in valid_columns:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        params.append(str(test_case_id))
        query = f"UPDATE testcases SET {', '.join(set_clauses)} WHERE uuid = ?"

        try:
            self.cursor.execute(query, tuple(params))
            if self.cursor.rowcount > 0:
                self.conn.commit()
                self._log_sync_operation(
                    "UPDATE", "testcases", test_case_id, test_case_data
                )
                logger.info(f"Successfully updated test case {test_case_id} locally.")
                return True
            else:
                logger.warning(f"Test case {test_case_id} not found locally.")
        except sqlite3.Error as e:
            logger.error("Failed to update test case in SQLite: %s", e, exc_info=True)

        return False

    async def delete_test_case(self, test_case_id: str) -> bool:  # Changed to str
        """Delete a test case via API."""
        logger.debug("Deleting test case with ID: %s", test_case_id)
        try:
            self.cursor.execute(
                "DELETE FROM testcases WHERE uuid = ?", (str(test_case_id),)
            )
            if self.cursor.rowcount > 0:
                self._log_sync_operation("DELETE", "testcases", test_case_id)
                self.save()
                return True
        except sqlite3.Error as e:
            logger.error("Failed to delete test case from SQLite: %s", e, exc_info=True)
        return False

    async def save_test_execution_result(
        self, execution_result: Dict
    ) -> Optional[Dict]:
        """
        Saves a test execution result by FETCHING the existing history,
        APPENDING the new result, and UPDATING the test case with the full list.
        """
        logger.debug(
            "Saving test execution result by updating history list: %s",
            execution_result,
        )
        if not self.current_user_token:
            logger.warning("Cannot save result: No authenticated user.")
            return None

        try:
            test_case_id = execution_result.get("testcase_id") or execution_result.get(
                "test_id"
            )
            project_id = execution_result.get("project_id")
            if not test_case_id or not project_id:
                logger.error("Cannot save result: test_case_id is missing.")
                return None

            all_test_cases = await self.get_test_cases(str(project_id), self.current_task.task_id)
            if not all_test_cases:
                logger.error(f"Failed to fetch test cases for project {project_id}.")
                return None

            current_test_case = None
            try:
                self.cursor.execute(
                    "SELECT test_result_details FROM testcases WHERE uuid = ?",
                    (str(test_case_id),),
                )
                row = self.cursor.fetchone()
                if row:
                    current_test_case = dict(row)
            except sqlite3.Error as e:
                logger.error(
                    "Failed to fetch test case from SQLite: %s", e, exc_info=True
                )
                return None

            if not current_test_case:
                logger.error(
                    f"Could not find test case {test_case_id} in project {project_id}."
                )
                return None

            history_list = current_test_case.get("test_result_details", [])
            if not isinstance(history_list, list):
                history_list = []
            
            # Extract checkpoint data
            checkpoint_data = execution_result.get("checkpoint_data")
            if checkpoint_data:
                logger.info(f"[DB save] Checkpoint data found for test case {test_case_id}.")
            checkpoint_json = json.dumps(checkpoint_data) if checkpoint_data else None

            new_history_item = {
                "status": execution_result.get("status", "unknown"),
                "start_time": execution_result.get("start_time", ""),
                "end_time": execution_result.get("end_time", ""),
                "error_message": execution_result.get("error_message", ""),
                "screenshots_count": len(execution_result.get("screenshots", [])),
                "execution_id": execution_result.get("execution_id", ""),
                "duration": execution_result.get("execution_duration"),
            }
            history_list.append(new_history_item)

            client_status = execution_result.get("status", "unknown")
            server_enum_status = "not_started"
            if client_status in ["passed", "completed"]:
                server_enum_status = "is_done"
            elif client_status in ["failed", "error"]:
                server_enum_status = "is_error"

            update_data = {
                "test_status": server_enum_status,
                # "test_result": client_status.title(),
                "last_run_status": client_status.title(),
                "last_run_time": execution_result.get("end_time"),
                "test_result_details": history_list,
                "checkpoint_data": checkpoint_json,
                "step_number": execution_result.get("step_number", 0),
            }

            response = await self.update_test_case(str(test_case_id), update_data)

            if response:
                logger.info(
                    "Successfully updated test case %s with new execution result",
                    test_case_id,
                )
                return update_data
            return None
        except Exception as e:
            logger.error("API save_test_execution_result failed: %s", e, exc_info=True)
            return None

    async def get_test_execution_results(
        self, project_id: str
    ) -> List[Dict]:  # Changed to str
        """Get test execution results for a project."""
        logger.debug("Fetching test execution results for project ID: %s", project_id)

        # Try API first
        if self.use_api and self.current_user_token:
            try:
                # If API has execution results endpoint, use it
                # For now, we'll get the test cases which include execution results
                test_cases = await self.get_test_cases(project_id, self.current_task.task_id)
                execution_results = []
                for tc in test_cases or []:
                    history_list = tc.get("test_result_details")
                    if isinstance(history_list, list):
                        for history_item in history_list:
                            history_item["testcase_id"] = tc.get("id") or tc.get("uuid")
                            history_item["test_name"] = tc.get(
                                "test_case", "Unknown Test"
                            )
                            execution_results.append(history_item)
                return execution_results
            except Exception:
                logger.error("API get_test_execution_results failed", exc_info=True)

        # Local storage fallback
        try:
            results_file = self.db_path.replace(".json", "_test_results.json")
            if os.path.exists(results_file):
                with open(results_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results = data.get("test_execution_results", [])
                    # Filter by project_id if provided
                    if project_id:
                        results = [
                            r
                            for r in results
                            if str(r.get("project_id"))
                            == str(project_id)  # Convert to str
                        ]
                    return results
        except Exception:
            logger.error("Local get_test_execution_results failed", exc_info=True)

        return []

    # --- Viewpoints Management ---

    def create_viewpoint_sync(self, viewpoint_data: Dict) -> Optional[Dict]:
        """Synchronous wrapper for create_viewpoint."""
        logger.debug("Synchronous call to create_viewpoint")
        try:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return loop.run_until_complete(self.create_viewpoint(viewpoint_data))
        except Exception:
            logger.error("Sync create_viewpoint failed", exc_info=True)
            return None

    def get_viewpoints_sync(self, project_id: Optional[str] = None) -> List[Dict]:
        """Synchronous wrapper for get_viewpoints."""
        logger.debug("Synchronous call to get_viewpoints")
        if not project_id and self.current_project:
            project_id = self.current_project.project_id
        if (
            not self.use_api
            or not self.viewpoints_service
            or not self.current_user_token
        ):
            logger.warning(
                "API mode is off or services/token not available. Cannot fetch viewpoints."
            )
            return []

        try:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                return loop.run_until_complete(self.get_viewpoints(project_id))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(self.get_viewpoints(project_id))
            return result if result is not None else []
        except Exception:
            logger.error("Sync get_viewpoints failed", exc_info=True)
            return []

    def update_viewpoint_sync(self, viewpoint_id: str, viewpoint_data: Dict) -> bool:
        """Synchronous wrapper for update_viewpoint."""
        try:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return bool(
                loop.run_until_complete(
                    self.update_viewpoint(viewpoint_id, viewpoint_data)
                )
            )
        except Exception:
            logger.error(
                "Sync update_viewpoint failed for ID %s", viewpoint_id, exc_info=True
            )
            return False

    async def create_viewpoint(self, viewpoint_data: Dict) -> Optional[Dict]:
        """Create a new viewpoint via API."""
        logger.debug("Creating viewpoint with data: %s", viewpoint_data)
        if not self.current_local_user_id or not self.current_project:
            logger.error(
                "Cannot create viewpoint: No authenticated local user or current project."
            )
            return None
        new_uuid = viewpoint_data.get("uuid") or viewpoint_data.get("viewpoint_id") or str(uuid.uuid4())
        viewpoint_data["uuid"] = new_uuid
        project_id = str(self.current_project.project_id)
        details_list = viewpoint_data.get("viewpoint_details", [])
        details_json = json.dumps(details_list)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        try:
            self.cursor.execute(
                """
                    INSERT INTO viewpoints (uuid, project_id, name, viewpoint_type, details_json, created_at, updated_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uuid) DO UPDATE SET
                        name = excluded.name,
                        viewpoint_type = excluded.viewpoint_type,
                        details_json = excluded.details_json,
                        updated_at = excluded.updated_at
                """,
                (
                    new_uuid,
                    project_id,
                    viewpoint_data.get("name", ""),
                    viewpoint_data.get("viewpoint_type", ""),
                    details_json,
                    now,
                    now,
                    self.current_local_user_id,
                ),
            )

            self._log_sync_operation("CREATE", "viewpoints", new_uuid, viewpoint_data)
            self.save()
            self.signals.viewpoints_changed.emit()
            return viewpoint_data
        except sqlite3.Error as e:
            logger.error("Failed to create viewpoint in SQLite: %s", e, exc_info=True)
            return None

    async def get_viewpoints(self, project_id: str) -> Optional[List[Dict]]:
        """Get all viewpoints via API."""
        logger.debug("Fetching all viewpoints")
        result = []
        try:
            self.cursor.execute(
                "SELECT * FROM viewpoints WHERE project_id = ?", (project_id,)
            )
            rows = self.cursor.fetchall()
            for row in rows:
                vp_dict = dict(row)
                details_json = vp_dict.pop("details_json", "[]")
                vp_dict["viewpoint_details"] = json.loads(details_json or "[]")
                result.append(vp_dict)
            return result
        except sqlite3.Error as e:
            logger.error("Failed to get viewpoints from SQLite: %s", e, exc_info=True)
            return []

    async def get_viewpoint(
        self, viewpoint_id: str
    ) -> Optional[Dict]:  # Changed to str
        """Get a specific viewpoint via API."""
        logger.debug("Fetching viewpoint with ID: %s", viewpoint_id)
        try:
            self.cursor.execute(
                "SELECT * FROM viewpoints WHERE uuid = ?", (viewpoint_id,)
            )
            row = self.cursor.fetchone()
            if row:
                vp_dict = dict(row)
                details_json = vp_dict.pop("details_json", "[]")
                vp_dict["viewpoint_details"] = json.loads(details_json or "[]")
                return vp_dict
        except sqlite3.Error as e:
            logger.error("Failed to get viewpoint from SQLite: %s", e, exc_info=True)
        return None

    async def update_viewpoint(self, viewpoint_id: str, viewpoint_data: Dict) -> bool:
        """Update a viewpoint"""
        detail_json = json.dumps(viewpoint_data.get("viewpoint_details", []))
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            self.cursor.execute(
                """
                    UPDATE viewpoints SET
                        name = ?, viewpoint_type = ?, details_json = ?, updated_at = ?
                    WHERE uuid = ?
                """,
                (
                    viewpoint_data.get("name", ""),
                    viewpoint_data.get("viewpoint_type", ""),
                    detail_json,
                    now,
                    viewpoint_id,
                ),
            )
            if self.cursor.rowcount > 0:
                self._log_sync_operation(
                    "UPDATE", "viewpoints", viewpoint_id, viewpoint_data
                )
                self.save()
                self.signals.viewpoints_changed.emit()
                return True
        except sqlite3.Error as e:
            logger.error("Failed to update viewpoint in SQLite: %s", e, exc_info=True)
        return False

    async def delete_viewpoint(self, viewpoint_id: str) -> bool:
        """Delete a viewpoint via API."""
        logger.debug("Deleting viewpoint with ID: %s", viewpoint_id)
        try:
            self.cursor.execute(
                "DELETE FROM viewpoints WHERE uuid = ?", (viewpoint_id,)
            )
            if self.cursor.rowcount > 0:
                self._log_sync_operation("DELETE", "viewpoints", viewpoint_id)
                self.save()
                self.signals.viewpoints_changed.emit()
                return True
        except sqlite3.Error as e:
            logger.error("Failed to delete viewpoint from SQLite: %s", e, exc_info=True)
        return False

    def delete_viewpoint_sync(self, viewpoint_id: str) -> bool:
        """Synchronous wrapper for delete_viewpoint."""
        logger.debug("Synchronous call to delete_viewpoint for ID: %s", viewpoint_id)
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            return bool(loop.run_until_complete(self.delete_viewpoint(viewpoint_id)))
        except Exception:
            logger.error(
                "Sync delete_viewpoint failed for ID %s", viewpoint_id, exc_info=True
            )
            return False

    # --- templates Management ---
    async def save_or_update_template(self, template_data: Dict) -> Optional[Dict]:
        """
        Saves or updates a template locally and logs for sync. 
        Scalable: Handles both new and existing templates through UPSERT.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        is_new = not bool(template_data.get("uuid"))
        template_uuid = template_data.get("uuid")
    
        template_data["uuid"] = template_uuid
        name = template_data.get("name", "Unnamed Template")
        vp_type = template_data.get("viewpoint_type")
        vp_type_str = vp_type.value if hasattr(vp_type, 'value') else str(vp_type)
        details_json = json.dumps(template_data.get("viewpoint_details", []))

        try:
            self.cursor.execute(
                """
                INSERT INTO viewpoints_templates (uuid, name, viewpoint_type, viewpoint_details, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(uuid) DO UPDATE SET
                    name = excluded.name,
                    viewpoint_type = excluded.viewpoint_type,
                    viewpoint_details = excluded.viewpoint_details,
                    updated_at = excluded.updated_at
                """,
                (template_uuid, name, vp_type_str, details_json, now, now)
            )
            
            action = "CREATE" if is_new else "UPDATE"
            self._log_sync_operation(action, "viewpoints_templates", template_uuid, template_data)
            self.save()
            
            logger.info(f"Template {action} successful: {template_uuid}")
            return template_data
            
        except sqlite3.Error as e:
            logger.error("Failed to save template in SQLite: %s", e, exc_info=True)
            return None

    def save_or_update_template_sync(self, template_data: Dict) -> Optional[Dict]:
        """Synchronous wrapper for save_or_update_template."""
        return asyncio.run(self.save_or_update_template(template_data))

    async def list_templates(self, viewpoint_type: ViewpointType) -> List[Dict]:
        """Fetch all templates filtered by type from local DB."""
        logger.debug(f"Fetching local templates for type: {viewpoint_type.value}")
        try:
            self.cursor.execute(
                "SELECT * FROM viewpoints_templates WHERE viewpoint_type = ?",
                (viewpoint_type.value,),
            )
            return [self._map_template_row(dict(row)) for row in self.cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Failed to list templates: %s", e, exc_info=True)
            return []
    
    def _map_template_row(self, row_dict: Dict) -> Dict:
        """Helper to sanitize and format DB rows for the application."""
        if row_dict.get("viewpoint_details"):
            try:
                row_dict["viewpoint_details"] = json.loads(row_dict["viewpoint_details"])
            except json.JSONDecodeError:
                row_dict["viewpoint_details"] = []
        return row_dict

    def list_templates_sync(self, viewpoint_type: ViewpointType) -> List[Dict]:
        """Synchronous wrapper for list_templates."""
        return asyncio.run(self.list_templates(viewpoint_type))

    async def delete_template(self, template_id: str) -> bool:
        """Delete template locally and log deletion for sync."""
        if not template_id: return False
        
        try:
            self.cursor.execute("DELETE FROM viewpoints_templates WHERE uuid = ?", (template_id,))
            if self.cursor.rowcount > 0:
                self._log_sync_operation("DELETE", "viewpoints_templates", template_id)
                self.save()
                logger.info(f"Template deleted locally: {template_id}")
                return True
            return False
        except sqlite3.Error as e:
            logger.error("Failed to delete template: %s", e, exc_info=True)
            return False

    def delete_template_sync(self, template_id: str) -> bool:
        """Synchronous wrapper for delete_template."""
        return asyncio.run(self.delete_template(template_id))
    
    # --- Configuration Methods ---

    def _is_valid_api_response(self, response: Any) -> bool:
        """Check if API response is valid and not None."""
        return response is not None

    def set_api_mode(self, use_api: bool, api_endpoint: Optional[str] = None):
        """
        Enable or disable API mode.

        Args:
            use_api: Whether to use API for operations
            api_endpoint: API endpoint URL (required if use_api is True)
        """
        self.use_api = use_api
        logger.info(
            "Setting API mode to %s with endpoint: %s", use_api, api_endpoint or "None"
        )
        if api_endpoint:
            self.api_endpoint = api_endpoint

        if self.use_api and self.api_endpoint:
            self.auth_service = AuthService(self.api_endpoint)
            self.project_service = ProjectService(self.api_endpoint)
            self.testcase_service = TestCaseService(self.api_endpoint)
            self.task_service = TaskService(self.api_endpoint)
            self.viewpoints_service = ViewpointsService(self.api_endpoint)
            self.templates_service = TemplateService(self.api_endpoint)
        else:
            self.auth_service = None
            self.project_service = None
            self.testcase_service = None
            self.task_service = None
            self.viewpoints_service = None
            self.templates_service = None

    def is_authenticated(self) -> bool:
        """Check if user is authenticated (has valid token)."""
        logger.debug("Checking if user is authenticated")
        # Check both local token and session manager
        return self.current_user_token is not None or session_manager.is_authenticated()

    async def sync_with_api(self) -> bool:
        """
        Synchronize local data with API.
        This method can be called to ensure local cache is up-to-date.
        """
        logger.debug("Syncing with API")
        if not self.use_api or not self.current_user_token:
            return False

        try:
            # Sync projects
            projects = await self.get_all_projects()
            logger.debug(
                "API sync received %d projects", len(projects) if projects else 0
            )
            if projects is not None:
                return True
        except Exception:
            logger.error("Sync with API failed", exc_info=True)

        return False

    def _ensure_authenticated(self):
        """Raises NotAuthenticatedError if the user is not logged in."""
        if not self.current_user_token:
            logger.warning("Operation failed: User is not authenticated.")
            raise NotAuthenticatedError("User is not authenticated.")

    def get_api_status(self) -> Dict[str, Any]:
        """Get the current API configuration and status."""
        logger.debug("Getting API status")
        return {
            "use_api": self.use_api,
            "api_endpoint": self.api_endpoint,
            "is_authenticated": self.is_authenticated(),
            "services_initialized": (
                all(
                    [
                        self.auth_service is not None,
                        self.project_service is not None,
                        self.testcase_service is not None,
                        self.viewpoints_service is not None,
                    ]
                )
                if self.use_api
                else False
            ),
        }
