from models.database import DataManager
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QDialogButtonBox,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from typing import List
from models.data_classes import Viewpoint, ViewpointType

from models.database import DataManager

from views.components.table import (
    DataTableWidget,
    TableModel,
    BaseColumnConfig,
    SelectColumnConfig,
    IndexColumnConfig,
    TextColumnConfig,
    SelectType,
    ActionColumnConfig,
)
from services.logging_config import get_logger
from views.components import ui_kit

logger = get_logger("viewpoint_template")


class AddFromTemplateDialog(QDialog):
    """
    A single-page dialog to select viewpoints from a master list of all templates,
    featuring search and a custom data table with advanced pagination.
    """

    def __init__(self, db: DataManager, viewpoint_type: ViewpointType, parent=None):
        super().__init__(parent)
        self.viewpoint_type = viewpoint_type
        self.db = db
        self.setWindowTitle("Add Viewpoints from Template")
        self.setMinimumSize(900, 700)

        # --- Data & State Management ---
        self.all_template_viewpoints: List[Viewpoint] = []
        self.filtered_viewpoints: List[Viewpoint] = []

        # --- UI Setup ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 20)
        main_layout.setSpacing(12)
        self._setup_ui(main_layout)

        # --- Button Box ---
        self.selected_count_label = QLabel("Selected: 0")
        self.selected_count_label.setObjectName("PaginationInfo")
        self.data_table.pagination_layout.insertWidget(0, self.selected_count_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.add_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.add_button.setText("Add Selected")
        self.cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.add_button.setObjectName("addButton")
        self.cancel_button.setObjectName("cancelButton")

        main_layout.addWidget(self.button_box)
        self._apply_stylesheet()

        # --- Connect Signals ---
        self.search_input.textChanged.connect(self._update_display)
        self.data_table.selection_changed.connect(self._update_add_button_state)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # --- Load Data and Initial Display ---
        self._load_all_data()
        self._update_display()
        self._update_add_button_state([])

    def _setup_ui(self, layout: QVBoxLayout):
        """Sets up the widgets using the new DataTableWidget."""
        label = ui_kit.label("Add viewpoints from templates", "CardTitle")
        hint = ui_kit.label("Select viewpoints from the list of available templates.", "MutedText")
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchLineEdit")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setPlaceholderText("Search by name or action description...")

        # --- DataTableWidget Setup ---
        self.table_model = TableModel([])

        column_configs: List[BaseColumnConfig] = [
            SelectColumnConfig(select_type=SelectType.MULTIPLE),
            IndexColumnConfig(header="No."),
            TextColumnConfig(
                header="Viewpoint Name",
                default_width=0.4,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            TextColumnConfig(
                header="Action Description",
                default_width=0.5,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            ActionColumnConfig(header="", min_width=60)
        ]

        self.data_table = DataTableWidget(
            column_configs=column_configs,
            model=self.table_model,
            items_per_page=20,
            item_height=44,
            header_height=44,
            highlight_selected_row=True,
            parent=self,
        )

        self.data_table.delete_requested.connect(self._handle_delete_row)

        # Add All Widgets to Main Layout
        layout.addWidget(label)
        layout.addWidget(hint)
        layout.addWidget(self.search_input)
        layout.addWidget(self.data_table)
        # The DataTableWidget includes its own pagination, so no need for manual controls.

    def _apply_stylesheet(self):
        """Buttons take their look from the global stylesheet (asset/buttons.qss)."""
        self.add_button.setObjectName("PrimaryButton")
        self.cancel_button.setObjectName("NeutralButton")
        ui_kit.repolish(self.add_button)
        ui_kit.repolish(self.cancel_button)

    def _load_all_data(self):
        """Fetches all template viewpoints from the DB into the master list."""
        try:
            viewpoints_data = self.db.list_templates_sync(
                viewpoint_type=self.viewpoint_type
            )
            self.all_template_viewpoints = [
                Viewpoint.from_dict(vp) for vp in viewpoints_data
            ]
        except Exception:  # If db or Viewpoint is not available for standalone run
            # Create dummy data for demonstration
            self.all_template_viewpoints = [
                Viewpoint(
                    viewpoint_id=str(i),
                    name=f"Template Viewpoint {i}",
                    viewpoint_details=[],
                )
                for i in range(1, 151)
            ]

    def _update_display(self):
        search_term = self.search_input.text().lower()
        if not search_term:
            self.filtered_viewpoints = self.all_template_viewpoints
        else:
            self.filtered_viewpoints = [
                vp for vp in self.all_template_viewpoints
                if search_term in vp.name.lower() or 
                (vp.description and search_term in vp.description.lower())
            ]

        table_data = []
        for vp in self.filtered_viewpoints:
            desc = getattr(vp, 'description', None)
            if not desc and vp.viewpoint_details:
                desc = vp.viewpoint_details[0].description_input
            
            table_data.append([None, None, vp.name, desc or ""])

        self.data_table.clear_selection()
        self.table_model.set_data(table_data)

    def _update_add_button_state(self, selected_indices: List[int]):
        """Enables the 'Add Selected' button only if rows are selected."""
        self.add_button.setEnabled(bool(selected_indices))
        count = len(selected_indices)
        self.selected_count_label.setText(f"Selected: {count}")

    def get_selected_viewpoints(self) -> List[Viewpoint]:
        """
        Gets the Viewpoint objects corresponding to the user's selected rows.
        Simplified for Local First architecture.
        """
        selected_indices = self.data_table.get_selected_row_indices()
        if not selected_indices:
            return []
        
        selected_viewpoints = [self.filtered_viewpoints[i] for i in selected_indices]
        return selected_viewpoints
    
    def _handle_delete_row(self, row_index: int):
        """Handles deletion of a template when the delete action is triggered from the table."""
        if not (0 <= row_index < len(self.filtered_viewpoints)):
            return
        
        target_template = self.filtered_viewpoints[row_index]
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete template '{target_template.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        
        success = self.db.delete_template_sync(target_template.viewpoint_id)
        if success:
            logger.info(f"Successfully deleted template {target_template.viewpoint_id}.")
            self._load_all_data()
            self._update_display() 
        else:
            logger.error(f"Failed to delete template {target_template.viewpoint_id}.")
            QMessageBox.warning(self, "Error", "Could not delete template.")