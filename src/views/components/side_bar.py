import os
import webbrowser
from typing import Dict, List, Optional

from dotenv import load_dotenv
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from asset import tokens
from services.logging_config import get_logger
from views.components import icons
from views.components.ui_kit import FixedSizeButton

load_dotenv()
logger = get_logger("sidebar")

EXPANDED_WIDTH = 248
COLLAPSED_WIDTH = 72

# Sidebar keys -> icon names from views/components/icons.py
NAV_ICONS = {
    "project_cms": "grid",
    "test_studio": "flask",
    "testcase_management": "list-check",
}

FEEDBACK_FALLBACK_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe5iQyWQHLaY4FHlNUX6GkHe5ronrVRkTC29mpSV8pCc83dGA/viewform?usp=dialog"


class NavButton(QPushButton):
    """A checkable navigation entry. Top-level entries show an icon."""

    def __init__(self, text: str, key: str, icon_name: Optional[str] = None, sub: bool = False, parent=None):
        super().__init__(text, parent)
        self.key = key
        self.full_text = text
        self.icon_name = icon_name
        self.setObjectName("NavSubItem" if sub else "NavItem")
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setIconSize(QSize(18, 18))
        self.toggled.connect(self._refresh_icon)
        self._refresh_icon(False)

    def _refresh_icon(self, checked: bool):
        if self.icon_name:
            color = tokens.PRIMARY_TEXT if checked else tokens.TEXT
            self.setIcon(icons.icon(self.icon_name, color, 18))

    def set_compact(self, compact: bool):
        self.setText("" if compact else self.full_text)
        self.setStyleSheet("text-align: center;" if compact else "")


class CurrentProjectCard(QFrame):
    """Shows the selected project's login details; the password is masked by default."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectCard")
        self._password = ""
        self._show_password = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head = QWidget()
        head.setObjectName("ProjectCardHead")
        head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        head_layout = QVBoxLayout(head)
        head_layout.setContentsMargins(12, 12, 12, 10)
        head_layout.setSpacing(2)
        caption = QLabel("Current project")
        caption.setObjectName("BrandCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.name_label = QLabel()
        self.name_label.setObjectName("BrandName")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.name_label.setWordWrap(True)
        head_layout.addWidget(caption)
        head_layout.addWidget(self.name_label)
        layout.addWidget(head)

        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(12, 10, 12, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        def key_label(text):
            lbl = QLabel(text)
            lbl.setObjectName("ProjectCardKey")
            return lbl

        def value_label():
            lbl = QLabel()
            lbl.setObjectName("ProjectCardValue")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return lbl

        self.url_label = value_label()
        self.login_label = value_label()
        self.password_label = value_label()

        self.eye_button = FixedSizeButton(22)
        self.eye_button.setObjectName("SidebarIconButton")
        self.eye_button.setStyleSheet("border: none;")
        self.eye_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.eye_button.clicked.connect(self._toggle_password)

        pw_row = QHBoxLayout()
        pw_row.setContentsMargins(0, 0, 0, 0)
        pw_row.addWidget(self.password_label, 1)
        pw_row.addWidget(self.eye_button)

        grid.addWidget(key_label("URL"), 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.url_label, 0, 1)
        grid.addWidget(key_label("Login ID"), 1, 0)
        grid.addWidget(self.login_label, 1, 1)
        grid.addWidget(key_label("Password"), 2, 0)
        grid.addLayout(pw_row, 2, 1)
        layout.addWidget(grid_box)

        self._render_password()

    def set_project(self, name: str, url: Optional[str], login_id: Optional[str], password: Optional[str]):
        self.name_label.setText(name or "")
        display_url = (url or "").split("://", 1)[-1]
        self.url_label.setText(
            self.url_label.fontMetrics().elidedText(display_url, Qt.TextElideMode.ElideRight, 140)
            if display_url else "—"
        )
        self.url_label.setToolTip(url or "")
        self.login_label.setText(login_id or "—")
        self._password = password or ""
        self._show_password = False
        self._render_password()

    def _toggle_password(self):
        self._show_password = not self._show_password
        self._render_password()

    def _render_password(self):
        if not self._password:
            self.password_label.setText("—")
            self.eye_button.setVisible(False)
            return
        self.eye_button.setVisible(True)
        self.password_label.setText(self._password if self._show_password else "•" * 8)
        name = "eye-off" if self._show_password else "eye"
        self.eye_button.setIcon(icons.icon(name, tokens.TEXT_MUTED, 14))
        tip = "Hide password" if self._show_password else "Show password"
        self.eye_button.setToolTip(tip)
        self.eye_button.setAccessibleName(tip)


class SidebarWidget(QWidget):
    """Main sidebar widget that controls navigation"""

    page_changed = Signal(str)
    setting_requested = Signal()

    def __init__(self, structure):
        super().__init__()
        self.structure = structure
        self.is_collapsed = False
        self._current_project_data: Dict[str, Optional[str]] = {}
        self._current_key: Optional[str] = None

        self.nav_buttons: Dict[str, NavButton] = {}
        self.group_parents: Dict[str, NavButton] = {}  # child key -> parent button
        self.group_children: Dict[str, List[str]] = {}  # parent key -> child keys
        self.group_containers: Dict[str, QWidget] = {}  # parent key -> sub-item container
        self.default_child: Dict[str, str] = {}

        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(EXPANDED_WIDTH)

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 20, 16, 16)
        root.setSpacing(20)

        # Brand row
        brand = QHBoxLayout()
        brand.setSpacing(10)
        self.brand_mark = QLabel()
        self.brand_mark.setObjectName("BrandMark")
        self.brand_mark.setFixedSize(34, 34)
        self.brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_mark.setPixmap(icons.pixmap("flask", "#FFFFFF", 20, 2))
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        self.brand_name = QLabel("Test Studio")
        self.brand_name.setObjectName("BrandName")
        self.brand_caption = QLabel("Test management")
        self.brand_caption.setObjectName("BrandCaption")
        brand_text.addWidget(self.brand_name)
        brand_text.addWidget(self.brand_caption)
        self.collapse_button = FixedSizeButton(30)
        self.collapse_button.setObjectName("SidebarIconButton")
        self.collapse_button.setIcon(icons.icon("panel", tokens.TEXT_MUTED, 16))
        self.collapse_button.setToolTip("Collapse sidebar")
        self.collapse_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.collapse_button.clicked.connect(self.toggle_sidebar)
        brand.addWidget(self.brand_mark)
        brand.addLayout(brand_text, 1)
        brand.addWidget(self.collapse_button)
        self.brand_text_widgets = [self.brand_name, self.brand_caption]
        root.addLayout(brand)

        # Navigation
        nav = QVBoxLayout()
        nav.setSpacing(2)
        self.section_label = QLabel("WORKSPACE")
        self.section_label.setObjectName("SectionLabel")
        self.section_label.setContentsMargins(10, 0, 0, 6)
        nav.addWidget(self.section_label)

        for tab in self.structure:
            key = tab["key"]
            parent_btn = NavButton(tab["name"], key, NAV_ICONS.get(key, "layers"))
            nav.addWidget(parent_btn)
            self.nav_buttons[key] = parent_btn
            children = tab.get("children") or []
            if children:
                container = QWidget()
                container.setObjectName("NavSubGroup")
                container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                sub_layout = QVBoxLayout(container)
                sub_layout.setContentsMargins(12, 2, 0, 2)
                sub_layout.setSpacing(2)
                wrapper = QHBoxLayout()
                wrapper.setContentsMargins(21, 0, 0, 4)
                wrapper.addWidget(container)
                nav.addLayout(wrapper)
                self.group_containers[key] = container
                self.group_children[key] = []
                for child in children:
                    child_btn = NavButton(child["name"], child["key"], sub=True)
                    sub_layout.addWidget(child_btn)
                    self.nav_buttons[child["key"]] = child_btn
                    self.group_parents[child["key"]] = parent_btn
                    self.group_children[key].append(child["key"])
                    if child.get("is_default"):
                        self.default_child[key] = child["key"]
                self.default_child.setdefault(key, children[0]["key"])

        for key, btn in self.nav_buttons.items():
            btn.clicked.connect(lambda _checked=False, k=key: self._on_nav_clicked(k))
        root.addLayout(nav)
        root.addStretch(1)

        # Current project
        self.project_card = CurrentProjectCard()
        self.project_card.hide()
        root.addWidget(self.project_card)

        # Footer: user + feedback + settings
        footer = QWidget()
        footer.setObjectName("SidebarFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.footer_layout = QHBoxLayout(footer)
        self.footer_layout.setContentsMargins(4, 12, 0, 0)
        self.footer_layout.setSpacing(8)
        self.avatar_label = QLabel("?")
        self.avatar_label.setObjectName("Avatar")
        self.avatar_label.setFixedSize(32, 32)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.username_label = QLabel("")
        self.username_label.setObjectName("UserName")
        self.feedback_button = self._footer_button("message", "Feedback", self._handle_feedback_click)
        self.settings_button = self._footer_button("settings", "Settings", self._handle_setting_click)
        self.footer_layout.addWidget(self.avatar_label)
        self.footer_layout.addWidget(self.username_label, 1)
        self.footer_layout.addWidget(self.feedback_button)
        self.footer_layout.addWidget(self.settings_button)
        root.addWidget(footer)

    def _footer_button(self, icon_name: str, tooltip: str, slot) -> QPushButton:
        btn = FixedSizeButton(32)
        btn.setObjectName("SidebarIconButton")
        btn.setIcon(icons.icon(icon_name, tokens.TEXT_MUTED, 16))
        btn.setToolTip(tooltip)
        btn.setAccessibleName(tooltip)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(slot)
        return btn

    # ------------------------------------------------------------ navigation
    def _on_nav_clicked(self, key: str):
        # A group header opens its default child page.
        if key in self.group_children:
            if self.is_collapsed:
                self.toggle_sidebar()
            key = self.default_child[key]
        self.set_current_page(key)

    def set_current_page(self, page_key: str):
        """
        Programmatically selects a tab or subtab by its unique key and emits
        page_changed, exactly like a user click.
        """
        if page_key in self.group_children:
            page_key = self.default_child[page_key]
        if page_key not in self.nav_buttons:
            logger.warning("Sidebar page with key '%s' not found.", page_key)
            return
        self._mark_selected(page_key)
        self.page_changed.emit(page_key)
        logger.debug("Emitted page change for key: %s", page_key)

    def _mark_selected(self, page_key: str):
        self._current_key = page_key
        parent_btn = self.group_parents.get(page_key)
        for key, btn in self.nav_buttons.items():
            # Group headers stay unchecked; their child shows the selection.
            btn.setChecked(key == page_key and key not in self.group_children)
        # In collapsed mode the group header stands in for its hidden children.
        if parent_btn is not None and self.is_collapsed:
            parent_btn.setChecked(True)

    def current_page_key(self) -> Optional[str]:
        return self._current_key

    def page_title(self, key: str) -> str:
        btn = self.nav_buttons.get(key)
        return btn.full_text if btn else key

    def parent_title(self, key: str) -> Optional[str]:
        parent = self.group_parents.get(key)
        return parent.full_text if parent else None

    # -------------------------------------------------------------- user / project
    def set_username(self, username: str):
        """Set the username displayed in the sidebar."""
        self.username_label.setText(username)
        initials = "".join(part[0] for part in username.replace("_", " ").split()[:2]).upper()
        self.avatar_label.setText(initials or "?")
        self.avatar_label.setToolTip(username)
        logger.debug("Sidebar username set to: %s", username)

    def set_current_project(
        self,
        project_name: str | None,
        login_url: str | None,
        login_id: str | None,
        password: str | None,
    ):
        self._current_project_data = {
            "name": project_name,
            "url": login_url,
            "id": login_id,
            "password": password,
        }
        if not project_name:
            self.project_card.hide()
            logger.debug("Hiding current project widget as no project is selected.")
            return
        self.project_card.set_project(project_name, login_url, login_id, password)
        self.project_card.setVisible(not self.is_collapsed)
        logger.debug("Sidebar current project details updated for: %s", project_name)

    def current_project_name(self) -> Optional[str]:
        return self._current_project_data.get("name")

    def on_project_changed(self, project: Optional["Project"]):  # noqa: F821
        if project:
            self.set_current_project(project.name, project.url, project.login_id, project.password)
        else:
            self.set_current_project(None, None, None, None)

    # ------------------------------------------------------------------ collapse
    def toggle_sidebar(self):
        """Collapses or expands the sidebar, hiding/showing elements."""
        self.is_collapsed = not self.is_collapsed
        compact = self.is_collapsed
        logger.debug("Sidebar toggled. Collapsed: %s", compact)

        self.setFixedWidth(COLLAPSED_WIDTH if compact else EXPANDED_WIDTH)
        for w in self.brand_text_widgets + [self.section_label, self.username_label, self.feedback_button]:
            w.setVisible(not compact)
        self.brand_mark.setVisible(not compact)
        self.collapse_button.setToolTip("Expand sidebar" if compact else "Collapse sidebar")
        for container in self.group_containers.values():
            container.setVisible(not compact)
        for key, btn in self.nav_buttons.items():
            if key not in self.group_parents:
                btn.set_compact(compact)
        self.project_card.setVisible(not compact and bool(self._current_project_data.get("name")))
        self.footer_layout.setDirection(
            QVBoxLayout.Direction.TopToBottom if compact else QVBoxLayout.Direction.LeftToRight
        )
        if self._current_key:
            self._mark_selected(self._current_key)

    # ------------------------------------------------------------------ actions
    def _handle_setting_click(self):
        """Handle setting button click"""
        logger.debug("Settings button clicked in sidebar")
        self.setting_requested.emit()

    def _handle_feedback_click(self):
        """Opens the feedback link from the environment variables."""
        url = os.getenv("FEEDBACK_URL", FEEDBACK_FALLBACK_URL)
        if not url:
            logger.warning("Feedback URL is not defined in .env and no fallback is available.")
            QMessageBox.warning(
                self,
                "Feedback Not Available",
                "The feedback link is not configured. Please contact support.",
            )
            return
        logger.info("Opening feedback form at: %s", url)
        webbrowser.open(url)
