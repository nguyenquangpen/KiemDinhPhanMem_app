from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QPixmap, QPalette, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,  # Import QLabel
    QMessageBox,
    QPushButton,
    QTreeWidgetItem,
    QWidget,
    QSizePolicy,
    QHBoxLayout,
)
import webbrowser
import os
from dotenv import load_dotenv
import resources_rc  # noqa: F401
from services.logging_config import get_logger
from ui.build.ui_sidebar import Ui_SidebarWidget
from ui.build.ui_sidebar_subtab import Ui_Form as Ui_SidebarSubtab
from ui.build.ui_sidebar_tab import Ui_Form as Ui_SidebarTab
from typing import Optional
from views.pages.sync_manager import SyncUI

load_dotenv()
logger = get_logger("sidebar")


class SidebarSubtab(QWidget):
    """Custom widget for sidebar subtabs"""

    def __init__(self, text="Subtab", is_last=False):
        super().__init__()
        self.ui = Ui_SidebarSubtab()
        self.ui.setupUi(self)
        self.ui.subTabNameLabel.setText(text)
        if is_last:
            end_tree_icon = QPixmap(":png/png/sidebar_subtab_line_end")
            self.ui.treeIconLabel.setPixmap(end_tree_icon)
        self._original_font_weight = self.ui.subTabNameLabel.font().weight()

    def set_bold(self, is_bold: bool):
        font = self.ui.subTabNameLabel.font()
        font.setWeight(QFont.Weight.Bold if is_bold else self._original_font_weight)
        self.ui.subTabNameLabel.setFont(font)


class SidebarTab(QWidget):
    def __init__(self, text="Tab", icon_path=None, is_selected=False, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarTab")
        self.setMaximumHeight(51)
        self.setAutoFillBackground(True)  # Tell the widget to fill its background
        palette = self.palette()
        palette.setColor(
            QPalette.ColorRole.Window, QColor("red")
        )  # Set the background color role
        self.setPalette(palette)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setObjectName("horizontalLayout")
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(10)

        self.selectIndicatorWidget = QWidget()
        self.selectIndicatorWidget.setObjectName("selectIndicatorWidget")
        self.selectIndicatorWidget.setFixedSize(QSize(3, 20))

        self.selectIndicatorWidget.setStyleSheet(
            "background-color: #56BB55; border-radius: 1px;"
        )
        policy = self.selectIndicatorWidget.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.selectIndicatorWidget.setSizePolicy(policy)

        self.iconLabel = QLabel()
        self.iconLabel.setObjectName("iconLabel")
        self.iconLabel.setFixedSize(20, 20)
        self.iconLabel.setScaledContents(True)

        if icon_path:
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                self.iconLabel.setPixmap(pixmap)
            else:
                logger.warning("Could not load icon from path: %s", icon_path)
        self.iconLabel.setVisible(bool(icon_path))

        self.tabNameLabel = QLabel(text)
        self.tabNameLabel.setObjectName("tabNameLabel")
        font = QFont()
        font.setFamilies(["Lexend Light", "Segoe UI", "Arial"])
        font.setPointSize(16)
        self.tabNameLabel.setFont(font)

        self.tabNameLabel.setVisible(False)

        self.main_layout.addWidget(self.selectIndicatorWidget)
        self.main_layout.addWidget(self.iconLabel)
        self.main_layout.addWidget(self.tabNameLabel)
        self.main_layout.addStretch()

        self.set_selected(is_selected)

    def set_text_visible(self, visible: bool):
        self.tabNameLabel.setVisible(visible)

    def set_selected(self, selected: bool):
        self.selectIndicatorWidget.setVisible(selected)

    def text(self) -> str:
        return self.tabNameLabel.text()


class SidebarWidget(QWidget):
    """Main sidebar widget that controls navigation"""

    page_changed = Signal(str)
    setting_requested = Signal()

    def __init__(self, structure):
        super().__init__()
        self.ui = Ui_SidebarWidget()
        self.ui.setupUi(self)

        self.structure = structure
        self.item_map = {}
        self.current_selected_tab_item = None
        self.current_selected_subtab_widget = None
        self.sync_settings_window = None
        self.is_collapsed = False
        self._current_project_data = {}
        if self._current_project_data and self._current_project_data.get("name"):
            self.ui.currentProjectWidget.show()
        else:
            self.ui.currentProjectWidget.hide()
        self.setup_tree_widget()
        self.ui.collapsedMinimizeButton.clicked.connect(self.toggle_sidebar)
        self.ui.settingButton.clicked.connect(self._handle_setting_click)
        self.ui.openMinimizeButton.clicked.connect(self.toggle_sidebar)
        self.ui.feedbackButton.clicked.connect(self._handle_feedback_click)
        self._update_setting_logout_minimize_buttons()

    def setup_tree_widget(self):
        """Set up the tree widget dynamically from the provided structure."""
        self.ui.treeWidget.clear()
        self.item_map.clear()
        self.ui.treeWidget.setHeaderHidden(True)
        self.ui.treeWidget.setRootIsDecorated(False)
        self.ui.treeWidget.setIndentation(0)
        self.ui.treeWidget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.ui.treeWidget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ui.treeWidget.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.ui.treeWidget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        default_page_key = None

        for tab_data in self.structure:
            is_default_tab = tab_data.get("is_default", False)
            tab_item = QTreeWidgetItem(self.ui.treeWidget)
            page_key = tab_data["key"]
            icon_path = tab_data.get("icon")
            tab_item.setData(0, Qt.ItemDataRole.UserRole, page_key)
            self.item_map[page_key] = tab_item

            tab_widget = SidebarTab(
                tab_data["name"], icon_path=icon_path, is_selected=is_default_tab
            )
            tab_widget.set_text_visible(not self.is_collapsed)

            self.ui.treeWidget.setItemWidget(tab_item, 0, tab_widget)

            if is_default_tab:
                self.current_selected_tab_item = tab_item
                default_page_key = page_key

            if "children" in tab_data:
                subtabs = tab_data["children"]
                num_subtabs = len(subtabs)

                for i, subtab_data in enumerate(subtabs):
                    is_default_subtab = subtab_data.get("is_default", False)
                    subtab_item = QTreeWidgetItem(tab_item)
                    sub_page_key = subtab_data["key"]
                    subtab_item.setData(0, Qt.ItemDataRole.UserRole, sub_page_key)
                    self.item_map[sub_page_key] = subtab_item

                    is_last = i == num_subtabs - 1
                    subtab_widget = SidebarSubtab(subtab_data["name"], is_last=is_last)
                    self.ui.treeWidget.setItemWidget(subtab_item, 0, subtab_widget)

                    if is_default_tab and is_default_subtab:
                        subtab_widget.set_bold(True)
                        self.current_selected_subtab_widget = subtab_widget
                        default_page_key = sub_page_key

                tab_item.setExpanded(is_default_tab)

        self.ui.treeWidget.itemClicked.connect(self.on_item_clicked)

        if default_page_key:
            self.page_changed.emit(default_page_key)

    def set_current_page(self, page_key: str):
        """
        Programmatically selects a tab or subtab by its unique key.
        This allows other parts of the application to change the sidebar's state.
        """
        item_to_select = self.item_map.get(page_key)

        if item_to_select:
            self.on_item_clicked(item_to_select, 0)
        else:
            logger.warning("Sidebar page with key '%s' not found.", page_key)

    def on_item_clicked(self, item, column):
        """Handle tree widget item clicks."""
        _ = column
        widget = self.ui.treeWidget.itemWidget(item, 0)
        page_key = item.data(0, Qt.ItemDataRole.UserRole)

        if (
            isinstance(widget, SidebarSubtab)
            and widget == self.current_selected_subtab_widget
        ) or (
            isinstance(widget, SidebarTab)
            and item == self.current_selected_tab_item
            and not item.childCount()
        ):
            return

        if isinstance(widget, SidebarTab):
            is_parent_tab = item.childCount() > 0
            if is_parent_tab:
                self.is_collapsed = True
                self.toggle_sidebar()

            self.update_tab_selection(item)
            if not is_parent_tab:
                self.clear_subtab_selection()

        elif isinstance(widget, SidebarSubtab):
            self.update_subtab_selection(widget)
            parent_item = item.parent()
            if parent_item:
                self.update_tab_selection(parent_item)

        if page_key:
            self.page_changed.emit(page_key)
            logger.debug("Emitted page change for key: %s", page_key)

    def update_tab_selection(self, selected_item):
        """Updates the green selection indicators for main tabs."""
        if self.current_selected_tab_item == selected_item:
            return

        if self.current_selected_tab_item:
            prev_widget = self.ui.treeWidget.itemWidget(
                self.current_selected_tab_item, 0
            )
            if isinstance(prev_widget, SidebarTab):
                prev_widget.set_selected(False)

        new_widget = self.ui.treeWidget.itemWidget(selected_item, 0)
        if isinstance(new_widget, SidebarTab):
            # REFACTOR: Use the widget's public API.
            new_widget.set_selected(True)
            self.current_selected_tab_item = selected_item
            if selected_item.childCount() > 0 and not self.is_collapsed:
                selected_item.setExpanded(True)

    def update_subtab_selection(self, selected_subtab_widget):
        """Updates the bold font for subtabs."""
        if self.current_selected_subtab_widget == selected_subtab_widget:
            return

        if self.current_selected_subtab_widget:
            self.current_selected_subtab_widget.set_bold(False)

        selected_subtab_widget.set_bold(True)
        self.current_selected_subtab_widget = selected_subtab_widget

    def clear_subtab_selection(self):
        if self.current_selected_subtab_widget:
            self.current_selected_subtab_widget.set_bold(False)
            self.current_selected_subtab_widget = None

    def set_username(self, username: str):
        """Set the username displayed in the sidebar."""
        if hasattr(self.ui, "usenameLabel"):
            self.ui.usenameLabel.setText(username)
            logger.debug("Sidebar username set to: %s", username)
        else:
            logger.warning("usenameLabel not found in sidebar UI")

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
            self.ui.currentProjectWidget.hide()
            logger.debug("Hiding current project widget as no project is selected.")
            return

        base_project_text = "Project Name: "
        base_url_text = "Login URL: "
        base_id_text = "Login ID: "
        base_password_text = "Password: "

        self.ui.currentProjectLabel.setText(f"{base_project_text} {project_name or ''}")
        self.ui.currentProjectLoginURLLabel.setText(
            f"{base_url_text} {login_url or ''}"
        )
        self.ui.currentProjectLoginIDLabel.setText(f"{base_id_text} {login_id or ''}")
        self.ui.currentProjectPasswordLabel.setText(
            f"{base_password_text} {password or ''}"
        )
        if not self.is_collapsed:
            self.ui.currentProjectWidget.show()
        logger.debug("Sidebar current project details updated for: %s", project_name)

    def on_project_changed(self, project: Optional ['Project']):
        if project:
            self.set_current_project(
                project.name, project.url, project.login_id, project.password
            )
        else:
            self.set_current_project(None, None, None, None)

    def toggle_sidebar(self):
        """Collapses or expands the sidebar, hiding/showing elements."""
        self.is_collapsed = not self.is_collapsed
        logger.debug("Sidebar toggled. Collapsed: %s", self.is_collapsed)

        # Toggle visibility of various static widgets
        self.ui.logoLabel.setPixmap(
            QPixmap(
                ":/png/png/cowell_short.png"
                if self.is_collapsed
                else ":/png/png/logo.png"
            )
        )
        self.ui.usenameLabel.setVisible(not self.is_collapsed)

        # Resize the avatar/username container
        self.ui.widget_2.setMaximumWidth(45 if self.is_collapsed else 16777215)

        # Handle project widget visibility
        if self.is_collapsed:
            self.ui.currentProjectWidget.hide()
        else:
            # Restore visibility based on whether a project is set
            if self._current_project_data and self._current_project_data.get("name"):
                self.ui.currentProjectWidget.show()
            else:
                self.ui.currentProjectWidget.hide()

        self._update_setting_logout_minimize_buttons()

        # Iterate through tree items to hide text and collapse/expand
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            item = self.ui.treeWidget.topLevelItem(i)
            if item:
                widget = self.ui.treeWidget.itemWidget(item, 0)

                if isinstance(widget, SidebarTab):
                    widget.set_text_visible(not self.is_collapsed)

                if self.is_collapsed:
                    item.setExpanded(False)

        # When expanding, restore the expanded state of the selected item
        if not self.is_collapsed:
            if (
                self.current_selected_tab_item
                and self.current_selected_tab_item.childCount() > 0
            ):
                self.current_selected_tab_item.setExpanded(True)

        # Set the main sidebar width
        if self.is_collapsed:
            self.setMinimumWidth(100)
            self.setMaximumWidth(100)
        else:
            self.setMinimumWidth(285)
            self.setMaximumWidth(285)

    def _update_setting_logout_minimize_buttons(self):
        self.ui.settingButton.setVisible(True)
        # Handle things
        # Không có đăng nhập nên ẩn nút Logout
        self.ui.collapsedLogoutButton.setVisible(False)
        self.ui.openLogoutButton.setVisible(False)
        if self.is_collapsed:

            self.ui.openMinimizeButton.setVisible(False)
            self.ui.collapsedMinimizeButton.setVisible(True)

            self.ui.settingHorizontalSpacer.changeSize(
                0, 0, QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            self.ui.settingButton.setText("")
            self.ui.feedBakcHorizontalSpacer.changeSize(
                0, 0, QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
            )
            self.ui.feedbackButton.setText("")
        else:
            self.ui.openMinimizeButton.setVisible(True)
            self.ui.collapsedMinimizeButton.setVisible(False)

            self.ui.settingHorizontalSpacer.changeSize(
                0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.ui.settingButton.setText("Settings")
            self.ui.feedBakcHorizontalSpacer.changeSize(
                0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.ui.feedbackButton.setText("Feedback")
            self.ui.controlContainerLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _handle_setting_click(self):
        """Handle setting button click"""
        logger.debug("Settings button clicked in sidebar")
        self.setting_requested.emit()

    def _handle_feedback_click(self):
        """Opens the feedback link from the environment variables."""
        # Define a fallback URL in case the environment variable is missing
        fallback_url = "https://docs.google.com/forms/d/e/1FAIpQLSe5iQyWQHLaY4FHlNUX6GkHe5ronrVRkTC29mpSV8pCc83dGA/viewform?usp=dialog"

        # Get the URL from the environment variable "FEEDBACK_URL", use fallback if not found
        url = os.getenv("FEEDBACK_URL", fallback_url)

        if not url:
            logger.warning(
                "Feedback URL is not defined in .env and no fallback is available."
            )
            QMessageBox.warning(
                self,
                "Feedback Not Available",
                "The feedback link is not configured. Please contact support.",
            )
            return

        logger.info("Opening feedback form at: %s", url)
        webbrowser.open(url)
