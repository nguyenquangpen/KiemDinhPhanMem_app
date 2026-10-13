# my_app/views/home.py
from typing import Union

from html import escape

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from asset import tokens

from models.data_classes import Project, User
from models.database import DataManager
from services.logging_config import get_logger
from ui.build.ui_main import Ui_MainWindow
from views.components.side_bar import SidebarWidget
from views.pages.component_viewpoint import ComponentViewpointWidget
from views.pages.page_viewpoint import PageViewpointWidget
from views.pages.project import ProjectWidget
from views.pages.project_cms import ProjectCMS
from views.pages.task import TaskWidget
from views.pages.testcases import TestCaseMainWindow
from views.pages.testcases_widget import TestCaseWidget
from views.pages.sync_manager import SyncUI

logger = get_logger("home")

SIDEBAR_STRUCTURE = [
    {
        "name": "Project CMS",
        "key": "project_cms",
        "is_default": True,
        "icon": ":/png/png/cms.png",
    },
    {
        "name": "Test Studio",
        "key": "test_studio",
        "icon": ":/png/png/test_tube.png",
        "children": [
            {"name": "Project", "key": "ts_project", "is_default": True},
            {"name": "Task", "key": "ts_task"},
            {"name": "Component Viewpoint", "key": "ts_component_vp"},
            {"name": "Page Viewpoint", "key": "ts_page_vp"},
        ],
    },
    {
        "name": "Testcase Management",
        "key": "testcase_management",
        "icon": ":/png/png/monitor.png",
    },
]


KEY_TAB_WIDGET_MAP = {
    "project_cms": ProjectCMS,
    "ts_project": ProjectWidget,
    "ts_task": TaskWidget,
    "testcase_management": TestCaseMainWindow,
    "ts_page_vp": PageViewpointWidget,
    "ts_component_vp": ComponentViewpointWidget,
}

PAGES_REQUIRING_PROJECT = {
    "ts_project": ProjectWidget,
    "ts_task": TaskWidget,
    "testcase_management": TestCaseMainWindow,
    "ts_page_vp": PageViewpointWidget,
    "ts_component_vp": ComponentViewpointWidget,
}

# Below this window width the sidebar collapses to icons so pages keep room for their tables.
AUTO_COLLAPSE_WIDTH = 1320
MIN_WINDOW_WIDTH = 1180


class MainWindow(QMainWindow):
    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.db = data_manager

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle("Test Management System")
        self.setMinimumWidth(MIN_WINDOW_WIDTH)
        self.resize(1360, 860)
        self._was_narrow = False
        self.sidebar_widget = SidebarWidget(SIDEBAR_STRUCTURE)
        self.top_bar = self._build_top_bar()

        # Cache to store created page widgets
        self.page_widgets = {}
        # Stacked widget to manage pages
        self.main_stacked_widget = QStackedWidget()

        self._integrate_widgets()
        self._connect_signals()
        self._set_initial_state()
        self.sync_settings_window = None
        logger.info("MainWindow initialized with sidebar and initial state set")

    def _integrate_widgets(self):
        logger.info("Integrating sidebar widget and stacked widget into MainWindow")
        self.ui.windowLayout.insertWidget(0, self.sidebar_widget)
        self.ui.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.ui.mainLayout.setSpacing(0)
        self.ui.mainLayout.addWidget(self.top_bar)
        # Add the stacked widget to the main layout to hold the content pages
        self.ui.mainLayout.addWidget(self.main_stacked_widget)
        self.ui.statusbar.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "sidebar_widget"):
            return
        # Only react when crossing the threshold, so a manual toggle is kept.
        narrow = self.width() < AUTO_COLLAPSE_WIDTH
        if narrow != getattr(self, "_was_narrow", False):
            self._was_narrow = narrow
            if narrow != self.sidebar_widget.is_collapsed:
                self.sidebar_widget.toggle_sidebar()

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(32, 0, 32, 0)
        self.breadcrumb_label = QLabel()
        self.breadcrumb_label.setObjectName("Breadcrumb")
        self.breadcrumb_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.breadcrumb_label, 1)
        return bar

    def _update_breadcrumb(self, *_args):
        """Projects / <project> / <task> / <page>, with the last part emphasised."""
        key = self.sidebar_widget.current_page_key() or "project_cms"
        parts = []
        if key == "project_cms":
            parts = ["Workspace", "Project CMS"]
        else:
            project = self.db.get_current_project()
            parts.append("Projects")
            if project:
                parts.append(project.name)
            if key == "testcase_management":
                task = self.db.get_current_task()
                if task and getattr(task, "task_name", ""):
                    parts.append(task.task_name)
                parts.append("Test cases")
            else:
                parts.append(self.sidebar_widget.page_title(key))
        sep = f'<span style="color:{tokens.TEXT_SUBTLE}">&nbsp;&nbsp;/&nbsp;&nbsp;</span>'
        head = sep.join(escape(p) for p in parts[:-1])
        last = f'<span style="color:{tokens.TEXT}; font-weight:500">{escape(parts[-1])}</span>'
        self.breadcrumb_label.setText(head + (sep if head else "") + last)

    def _connect_signals(self):
        logger.info("Connecting signals for MainWindow")
        self.sidebar_widget.page_changed.connect(self._on_tab_selected)
        self.sidebar_widget.setting_requested.connect(self._handle_setting_click)
        self.db.signals.current_project_changed.connect(self.sidebar_widget.on_project_changed)
        self.db.signals.current_project_changed.connect(self._update_breadcrumb)
        self.db.signals.current_task_changed.connect(self._update_breadcrumb)

    def _set_initial_state(self):
        logger.info("Setting initial state for MainWindow")
        # Programmatically set the initial page, which will trigger _on_tab_selected
        self.sidebar_widget.set_current_page("project_cms")

    def set_user_info(self, user: Union[User, dict]):
        """Set user information including username in the sidebar."""
        if user:
            # Handle both dict and object forms of user info
            if isinstance(user, dict):
                username = user.get("username", "Unknown User")
            else:
                username = getattr(user, "username", "Unknown User")

            logger.info("Setting username in sidebar: %s", username)
            self.sidebar_widget.set_username(username)
        else:
            logger.warning("No user info provided to set_user_info")

    @Slot(str)
    def _on_tab_selected(self, key: str):
        """
        Switches to the widget corresponding to the given key.
        Creates the widget if it doesn't exist yet.
        """
        logger.info("Tab selected: '%s'", key)

        if key in PAGES_REQUIRING_PROJECT and not self.db.get_current_project():
            QMessageBox.warning(
                self,
                "No project selected yet",
                "Please select or create a project before accessing this page.",
            )
            self.sidebar_widget.set_current_page("project_cms")
            return
        
        if key == "testcase_management" and not self.db.get_current_task():
            QMessageBox.warning(
                self,
                "No task select",
                "Please select a Task in the 'Task' page before viewing the Testcase.",
            )
            self.sidebar_widget.set_current_page("ts_task")
            return
        # Check if the widget has been created before
        if key not in self.page_widgets:
            if key not in KEY_TAB_WIDGET_MAP:
                logger.warning("No widget mapped for key: %s", key)
                return

            # Create the widget instance since it doesn't exist
            widget_class = KEY_TAB_WIDGET_MAP[key]
            widget_instance = widget_class(self.db, parent=self)
            logger.debug(
                "Creating new widget instance for key '%s': %s",
                key,
                widget_class.__name__,
            )

            if isinstance(widget_instance, (PageViewpointWidget, ComponentViewpointWidget)):
                widget_instance.viewpoints_updated.connect(self._on_viewpoints_changed)

            # Store the new widget in the cache and add it to the stacked widget
            self.page_widgets[key] = widget_instance
            self.main_stacked_widget.addWidget(widget_instance)

            if isinstance(widget_instance, ProjectCMS):
                widget_instance.project_selected.connect(self._on_project_selected)
                widget_instance.project_created.connect(self._on_project_selected)
                widget_instance.project_edit.connect(self._on_project_edited)
                
            elif isinstance(widget_instance, ProjectWidget):
                widget_instance.view_testcases_requested.connect(
                    self._on_view_testcase_on_project
                )
                widget_instance.edit_task_requested.connect(
                    self._on_task_edit_requested_on_project
                )
                widget_instance.add_task_requested.connect(
                    self._on_add_task_requested_on_project
                )
                widget_instance.open_viewpoints_requested.connect(
                    lambda: self.sidebar_widget.set_current_page("ts_component_vp")
                )

        # Retrieve the widget (either newly created or from cache)
        widget_to_show = self.page_widgets[key]

        current_project = self.db.get_current_project()

        if isinstance(
            widget_to_show,
            (
                ProjectWidget,
                TaskWidget,
                ComponentViewpointWidget,
                PageViewpointWidget,
            ),
        ):
            if current_project and current_project.project_id:
                logger.debug(
                    f"Passing current project '{current_project.name}' to widget {type(widget_to_show).__name__}"
                )

                self.db.set_current_project_sync(current_project.project_id)
            else:
                logger.debug(
                    f"No current project set for widget {type(widget_to_show).__name__}"
                )
        # if isinstance(widget_to_show, TaskWidget):
        #     self.sidebar_widget.page_changed.connect(
        #         widget_to_show._refresh_viewpoint_data
        #     )
        # --- Data Refresh Logic ---
        # This part ensures data is up-to-date when switching back to a view
        if isinstance(
            widget_to_show, (ProjectWidget, TestCaseWidget, TestCaseMainWindow)
        ):
            logger.debug(
                "Refreshing data for widget: %s", widget_to_show.__class__.__name__
            )
            widget_to_show.refresh_project_data()

        # Set the current widget in the stack to be visible
        self.main_stacked_widget.setCurrentWidget(widget_to_show)
        self._update_breadcrumb()

    @Slot()
    def _on_viewpoints_changed(self):
        logger.info("Viewpoints data has changed. Requesting TaskWidget to refresh.")
        if "ts_task" in self.page_widgets:
            task_widget = self.page_widgets["ts_task"]
            if isinstance(task_widget, TaskWidget):
                task_widget._refresh_viewpoint_data()

    @Slot()
    def _on_view_testcase_on_project(self):
        self.sidebar_widget.set_current_page("testcase_management")

    @Slot()
    def _on_task_edit_requested_on_project(self):
        self.sidebar_widget.set_current_page("ts_task")
    
    @Slot()
    def _on_add_task_requested_on_project(self):
        """
        Handles the request to create a new task.
        Navigates to the Task page without preselecting any task.
        """
        logger.info("Add task requested. Switching to 'ts_task' page.")

        self.sidebar_widget.set_current_page("ts_task")

    @Slot(Project)
    def _on_project_selected(self, project: Project):
        """
        Handles when a project is selected or newly created from the ProjectCMS page.
        This slot now updates the DataManager before switching the page.
        """
        logger.info(
            "Signal received for project: '%s'. Setting as current and "
            "switching to 'ts_project' view.",
            project.name,
        )
        if project:
            logger.debug(
                "Setting current project in DataManager: %s", project.project_id
            )
            self.db.set_current_project_sync(
                project.project_id if project.project_id is not None else ""
            )

        self.sidebar_widget.set_current_project(
            project_name=project.name,
            login_url=project.url,
            login_id=project.login_id,
            password=project.password,
        )

        self.sidebar_widget.set_current_page("ts_project")

    @Slot(Project)
    def _on_project_edited(self, project: Project):
        """
        Handles when a project is edited in ProjectCMS.
        Unlike selection, this does NOT navigate away from the CMS page —
        it only refreshes related widgets and updates sidebar info.
        """
        logger.info("Project edited: %s", project.name)

        self.db.set_current_project_sync(
            project.project_id if project.project_id is not None else ""
        )

        self.sidebar_widget.set_current_project(
            project_name=project.name,
            login_url=project.url,
            login_id=project.login_id,
            password=project.password,
        )

        project_widget = self.page_widgets.get("ts_project")
        if project_widget:
            logger.debug("Refreshing ProjectWidget data after edit")
            project_widget.refresh_project_data()

        for key in ["ts_task", "testcase_management", "ts_page_vp", "ts_component_vp"]:
            w = self.page_widgets.get(key)
            if w:
                logger.debug(f"Refreshing {key} after project edit")
                w.refresh_project_data()


    def _handle_setting_click(self):
        """Handle setting button click"""
        logger.debug("Settings button clicked in MainWindow")
        if not self.sync_settings_window:
            self.sync_settings_window = SyncUI(self.db, parent=self)
        self.sync_settings_window.show()
        self.sync_settings_window.raise_()
        self.sync_settings_window.activateWindow()
        logger.info("Settings window opened")