# my_app/models/data_classes.py
import datetime
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TestcaseStatus(Enum):
    """Enumeration for the execution status of a TestCase."""

    PENDING = "Pending"
    PASSED = "Passed"
    FAILED = "Failed"
    BLOCKED = "Blocked"
    SKIPPED = "Skipped"


class ViewpointType(Enum):
    PAGE = "page"
    COMPONENT = "component"


class TaskStatus(Enum):
    """Enumeration for Celery task states."""

    PENDING = "PENDING"
    STARTED = "STARTED"
    RETRY = "RETRY"
    FAILURE = "FAILURE"
    SUCCESS = "SUCCESS"
    RUNNING = "RUNNING"


@dataclass
class User:
    """Represents a user of the system. Passwords are handled securely."""

    username: str
    password: str

    user_id: Optional[str] = None  # Made optional

    user_id: str | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        return cls(
            user_id=(
                str(data.get("user_id")) if data.get("user_id") else None
            ),  # Handle None case
            username=data.get("username", ""),
            password=data.get("password", ""),
        )


@dataclass
class ViewpointDescription:
    description_input: str
    error_message_expected: str
    final_result_expected: str
    detail_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description_input": self.description_input,
            "error_message_expected": self.error_message_expected,
            "final_result_expected": self.final_result_expected,
            "detail_id": self.detail_id 
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ViewpointDescription":
        detail_id = data.get("uuid") or data.get("detail_id")
        return cls(
            detail_id=detail_id,
            description_input=data.get("description_input", ""),
            error_message_expected=data.get("error_message_expected", ""),
            final_result_expected=data.get("final_result_expected", ""),
        )


@dataclass
class Viewpoint:
    """DTO for a viewpoint, which groups related test details."""

    name: str
    viewpoint_details: List[ViewpointDescription] = field(default_factory=list)
    viewpoint_type: Optional[ViewpointType] = None
    viewpoint_id: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    created_by: Optional[str] = None
    project_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "viewpoint_type": (
                self.viewpoint_type.value if self.viewpoint_type is not None else None
            ),
            "viewpoint_details": [vd.to_dict() for vd in self.viewpoint_details],
            "viewpoint_id": self.viewpoint_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "project_id": self.project_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Viewpoint":
        viewpoint_type_str = str(data.get("viewpoint_type", "page")).lower()
        try:
            viewpoint_type = ViewpointType(viewpoint_type_str)
        except ValueError:
            viewpoint_type = ViewpointType.PAGE  # default fallback
        
        def parse_dt(dt_str):
            if not dt_str: return None
            try:
                return datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None

        return cls(
            name=data.get("name", ""),
            viewpoint_type=viewpoint_type,
            viewpoint_details=[
                ViewpointDescription.from_dict(vd)
                for vd in data.get("viewpoint_details", [])
            ],
            viewpoint_id=data.get("uuid"),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
            created_by=str(data.get("created_by")) if data.get("created_by") else None,
            project_id=str(data.get("project_id")) if data.get("project_id") else None,
        )


@dataclass
class Testcase:
    """Represents a single, executable test case."""

    title: str
    description: str = ""
    steps: List[str] = field(default_factory=list)
    expected_result: str = ""
    actual_result: str = ""
    status: TestcaseStatus = TestcaseStatus.PENDING
    executed_by_user_id: Optional[str] = None
    execution_date: Optional[datetime.datetime] = None

    test_case_id: Optional[str] = None  # Made optional

    # Additional fields based on API schema
    test_field: str = ""
    test_type: str = ""
    test_case: str = ""  # This might be the same as title
    test_reference: str = ""
    test_expect: str = ""  # This might be the same as expected_result

    def execute(self, status: TestcaseStatus, actual_result: str, user: User):
        """Marks the test case as executed, updating its state."""
        self.status = status
        self.actual_result = actual_result
        self.executed_by_user_id = user.user_id
        self.execution_date = datetime.datetime.now(datetime.timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        # Map to API schema field names
        status_mapping = {
            TestcaseStatus.PENDING: "not_started",
            TestcaseStatus.PASSED: "is_done",
            TestcaseStatus.FAILED: "is_error",
            TestcaseStatus.BLOCKED: "is_error",
            TestcaseStatus.SKIPPED: "not_started",
        }

        return {
            "test_case_id": str(self.test_case_id),
            "title": self.title,
            "description": self.description,
            "steps": self.steps,
            "expected_result": self.expected_result,
            "actual_result": self.actual_result,
            "status": self.status.value,
            "test_status": status_mapping.get(self.status, "not_started"),  # API field
            "executed_by_user_id": self.executed_by_user_id,
            "execution_date": (
                self.execution_date.isoformat() if self.execution_date else None
            ),
            # API specific fields
            "test_field": self.test_field,
            "test_type": self.test_type,
            "test_case": self.test_case or self.title,  # fallback to title
            "test_reference": self.test_reference,
            "test_expect": self.test_expect
            or self.expected_result,  # fallback to expected_result
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Testcase":
        # Handle execution date
        exec_date_str = data.get("execution_date")
        exec_date = None
        if exec_date_str:
            try:
                exec_date = datetime.datetime.fromisoformat(
                    exec_date_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                exec_date = None

        # Handle status mapping from API
        api_status = data.get("test_status")
        status = TestcaseStatus.PENDING  # default

        if api_status == "is_done":
            status = TestcaseStatus.PASSED
        elif api_status == "is_error":
            status = TestcaseStatus.FAILED
        elif api_status == "not_started":
            status = TestcaseStatus.PENDING
        elif data.get("status"):
            try:
                status = TestcaseStatus(data["status"])
            except ValueError:
                status = TestcaseStatus.PENDING

        return cls(
            test_case_id=(
                str(data.get("test_case_id")) if data.get("test_case_id") else None
            ),  # Handle None case
            title=data.get("title", ""),
            description=data.get("description", ""),
            steps=data.get("steps", []),
            expected_result=data.get("expected_result", ""),
            actual_result=data.get("actual_result", ""),
            status=status,
            executed_by_user_id=(
                str(data["executed_by_user_id"])
                if data.get("executed_by_user_id")
                else None
            ),
            execution_date=exec_date,
            # API specific fields
            test_field=data.get("test_field", ""),
            test_type=data.get("test_type", ""),
            test_case=data.get("test_case", ""),
            test_reference=data.get("test_reference", ""),
            test_expect=data.get("test_expect", ""),
        )


@dataclass
class Spec:
    """Represents a spec of a task, a task can have multiple specs"""

    name: str
    required: bool
    min: int
    max: int
    specification: str
    default_value: str
    validation_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_name": self.name,
            "required": self.required,
            "min": self.min,
            "max": self.max,
            "spec": self.specification,
            "default": self.default_value,  # API uses 'default'
            "validation_types": self.validation_types,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Spec":
        # Handle validation_type - it might be a dict or a list of strings
        raw_validation_types = data.get("validation_types", [])

        return cls(
            # Look for 'item_name' first
            name=data.get("item_name") or data.get("name") or data.get("field", ""),
            required=data.get("required", False),
            min=data.get("min") or 0,
            max=data.get("max") or 0,
            # Look for 'spec' first
            specification=data.get("spec")
            or data.get("specification")
            or data.get("description", ""),
            default_value=data.get("default_value") or data.get("default", ""),
            validation_types=raw_validation_types,
        )


@dataclass
class Task:
    """Represents a task or test suite within a project."""

    task_id: Optional[str] = None  # Made optional
    test_cases: List[Testcase] = field(default_factory=list)
    specs: List[Spec] = field(default_factory=list)

    # Additional fields from API
    url_test: str = ""
    task_name: str = ""  # This might be the same as name
    viewpoint_id: str = ""
    project_id: Optional[str] = None
    request_login: bool = False

    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    created_by: Optional[str] = None
    celery_task_id: Optional[str] = None
    generation_started_at: Optional[datetime.datetime] = None
    generation_status: Optional[str] = None
    include_component_viewpoints: bool = False

    @property
    def total_testcase_count(self) -> int:
        return len(self.test_cases)

    @property
    def ok_testcase_count(self) -> int:
        return sum(1 for tc in self.test_cases if tc.status == TestcaseStatus.PASSED)

    @property
    def ng_testcase_count(self) -> int:
        return sum(1 for tc in self.test_cases if tc.status == TestcaseStatus.FAILED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_name": self.task_name,
            "specs": [s.to_dict() for s in self.specs],
            "items": [s.to_dict() for s in self.specs],  # API uses 'items' for specs
            # API specific fields
            "url_test": self.url_test,
            "viewpoint_id": self.viewpoint_id,
            "project_id": self.project_id,
            "request_login": self.request_login,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "celery_task_id": self.celery_task_id,
            "generation_started_at": self.generation_started_at.isoformat() if self.generation_started_at else None,
            "generation_status": self.generation_status,
            "include_component_viewpoints": self.include_component_viewpoints,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        # Handle specs from either 'specs' or 'items'
        specs_data = data.get("specs", []) or data.get("items", [])
        specs = []
        for spec_data in specs_data:
            try:
                specs.append(Spec.from_dict(spec_data))
            except ValueError:
                # Skip invalid specs that don't have proper validation_type
                continue
        
        def parse_dt(dt_str):
            if not dt_str: 
                return None
            if isinstance(dt_str, datetime.datetime):
                return dt_str
            try:
                return datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None

        return cls(
            task_id=(
                str(data.get("uuid")) if data.get("uuid") else None
            ),  # Handle None case
            task_name=data.get("task_name", ""),
            specs=specs,
            test_cases=[Testcase.from_dict(tc) for tc in data.get("test_cases", [])],
            # API specific fields
            url_test=data.get("url_test", ""),
            viewpoint_id=data.get("viewpoint_id", ""),
            project_id=data.get("project_id"),
            request_login=data.get("request_login", False),
            
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
            created_by=str(data.get("created_by")) if data.get("created_by") else None,
            celery_task_id=data.get("celery_task_id"),
            generation_started_at=parse_dt(data.get("generation_started_at")),
            generation_status=data.get("generation_status"),
            include_component_viewpoints=data.get("include_component_viewpoints", False),
        )

@dataclass
class Project:
    """Represents a single project, the main container for testing activities."""

    name: str
    url: str = ""
    description: str = ""
    login_id: str = ""
    password: str = field(repr=False, default="")
    tasks: List[Task] = field(default_factory=list)
    testcase_specification: List[Dict[str, Any]] = field(default_factory=list)

    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    created_by: Optional[str] = None
    testcase_generated: bool = False

    project_id: Optional[str] = None  # Made optional

    @property
    def total_testcase_count(self) -> int:
        return sum(task.total_testcase_count for task in self.tasks)

    @property
    def executed_testcase_count(self) -> int:
        return self.ok_testcase_count + self.ng_testcase_count

    @property
    def ok_testcase_count(self) -> int:
        return sum(task.ok_testcase_count for task in self.tasks)

    @property
    def ng_testcase_count(self) -> int:
        return sum(task.ng_testcase_count for task in self.tasks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.project_id,  # API uses 'uuid'
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "login_id": self.login_id,
            "password": self.password,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "testcase_generated": self.testcase_generated,
            "tasks": [t.to_dict() for t in self.tasks],
            "testcase_specification": self.testcase_specification,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        # Handle project ID from multiple possible fields
        project_id_str = data.get("uuid") or data.get("project_id") or data.get("id")
        if not project_id_str:
            project_id_str = str(uuid.uuid4())  # Generate if missing

        def parse_dt(dt_str):
            if not dt_str:
                return None
            try:
                # Handle format: 2025-11-16T01:54:52.024+00:00
                return datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None

        return cls(
            project_id=str(project_id_str),
            name=data.get("name", ""),
            url=data.get("url", ""),
            description=data.get("description", ""),
            login_id=data.get("login_id", ""),
            password=data.get("password", ""),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
            created_by=str(data["created_by"]) if data.get("created_by") else None,
            testcase_generated=data.get("testcase_generated", False),
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            testcase_specification=data.get("testcase_specification", []),
        )


@dataclass
class Screenshot:
    """Represents a screenshot taken during test execution."""

    file_path: str
    step_name: str
    timestamp: datetime.datetime
    description: str = ""
    file_size: int = 0

    screenshot_id: Optional[str] = None  # Made optional
    testcase_id: Optional[str] = None  # Made optional

    def to_dict(self) -> Dict:
        return {
            "screenshot_id": self.screenshot_id,
            "testcase_id": self.testcase_id,
            "file_path": self.file_path,
            "step_name": self.step_name,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "file_size": self.file_size,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Screenshot":
        timestamp_str = data.get("timestamp", "")
        timestamp = datetime.datetime.now(datetime.timezone.utc)

        if timestamp_str:
            try:
                timestamp = datetime.datetime.fromisoformat(
                    timestamp_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        return cls(
            screenshot_id=(
                str(data.get("screenshot_id")) if data.get("screenshot_id") else None
            ),  # Handle None case
            testcase_id=(
                str(data.get("testcase_id")) if data.get("testcase_id") else None
            ),  # Handle None case
            file_path=data.get("file_path", ""),
            step_name=data.get("step_name", ""),
            timestamp=timestamp,
            description=data.get("description", ""),
            file_size=data.get("file_size", 0),
        )


@dataclass
class TestExecutionResult:
    """Represents the result of a test case execution."""

    status: TestcaseStatus
    start_time: datetime.datetime
    end_time: Optional[datetime.datetime] = None
    error_message: str = ""
    error_log: str = ""
    screenshots: List[Screenshot] = field(default_factory=list)
    executed_by_user_id: Optional[str] = None

    execution_id: Optional[str] = None  # Made optional
    testcase_id: Optional[str] = None  # Made optional
    project_id: Optional[str] = None  # Made optional

    @property
    def duration(self) -> Optional[float]:
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def is_completed(self) -> bool:
        return self.status in [
            TestcaseStatus.PASSED,
            TestcaseStatus.FAILED,
            TestcaseStatus.BLOCKED,
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "testcase_id": self.testcase_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error_message": self.error_message,
            "error_log": self.error_log,
            "screenshots": [s.to_dict() for s in self.screenshots],
            "executed_by_user_id": self.executed_by_user_id,
            "duration": self.duration,
            "is_completed": self.is_completed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestExecutionResult":
        # Parse timestamps
        start_time_str = data.get("start_time", "")
        end_time_str = data.get("end_time")

        start_time = datetime.datetime.now(datetime.timezone.utc)
        if start_time_str:
            try:
                start_time = datetime.datetime.fromisoformat(
                    start_time_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        end_time = None
        if end_time_str:
            try:
                end_time = datetime.datetime.fromisoformat(
                    end_time_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        # Parse status
        status = TestcaseStatus.PENDING
        if data.get("status"):
            try:
                status = TestcaseStatus(data["status"])
            except ValueError:
                pass

        return cls(
            execution_id=(
                str(data.get("execution_id")) if data.get("execution_id") else None
            ),  # Handle None case
            testcase_id=(
                str(data.get("testcase_id")) if data.get("testcase_id") else None
            ),  # Handle None case
            project_id=(
                str(data.get("project_id")) if data.get("project_id") else None
            ),  # Handle None case
            status=status,
            start_time=start_time,
            end_time=end_time,
            error_message=data.get("error_message", ""),
            error_log=data.get("error_log", ""),
            screenshots=[Screenshot.from_dict(s) for s in data.get("screenshots", [])],
            executed_by_user_id=(
                str(data["executed_by_user_id"])
                if data.get("executed_by_user_id")
                else None
            ),
        )


@dataclass
class TestReport:
    """Represents a complete test report for a project."""

    project_name: str
    generated_at: datetime.datetime
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    blocked_tests: int = 0
    skipped_tests: int = 0
    execution_results: List[TestExecutionResult] = field(default_factory=list)

    report_id: Optional[str] = None  # Made optional
    project_id: Optional[str] = None  # Made optional

    @property
    def success_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed_tests / self.total_tests) * 100.0

    @property
    def executed_tests(self) -> int:
        return self.passed_tests + self.failed_tests + self.blocked_tests

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "generated_at": self.generated_at.isoformat(),
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "blocked_tests": self.blocked_tests,
            "skipped_tests": self.skipped_tests,
            "execution_results": [er.to_dict() for er in self.execution_results],
            "success_rate": self.success_rate,
            "executed_tests": self.executed_tests,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestReport":
        # Parse generated_at timestamp
        generated_at_str = data.get("generated_at", "")
        generated_at = datetime.datetime.now(datetime.timezone.utc)

        if generated_at_str:
            try:
                generated_at = datetime.datetime.fromisoformat(
                    generated_at_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        return cls(
            report_id=(
                str(data.get("report_id")) if data.get("report_id") else None
            ),  # Handle None case
            project_id=(
                str(data.get("project_id")) if data.get("project_id") else None
            ),  # Handle None case
            project_name=data.get("project_name", ""),
            generated_at=generated_at,
            total_tests=data.get("total_tests", 0),
            passed_tests=data.get("passed_tests", 0),
            failed_tests=data.get("failed_tests", 0),
            blocked_tests=data.get("blocked_tests", 0),
            skipped_tests=data.get("skipped_tests", 0),
            execution_results=[
                TestExecutionResult.from_dict(er)
                for er in data.get("execution_results", [])
            ],
        )
