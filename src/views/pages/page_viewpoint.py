from PySide6.QtWidgets import QWidget, QVBoxLayout, QDialog, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QEvent, Signal

from typing import List, Tuple, Any

from models.data_classes import Viewpoint, ViewpointDescription, ViewpointType, Project
from models.database import DataManager
from views.components.table import (
    ActionColumnConfig,
    DataTableWidget,
    IndexColumnConfig,
    TableModel,
    TextColumnConfig,
    RowContext,
)
from services.logging_config import get_database_logger
from views.dialog.viewpoint_template import AddFromTemplateDialog

logger = get_database_logger()

class PageViewpointWidget(QWidget):

    viewpoints_updated = Signal()

    def __init__(self, db: DataManager, parent):
        super().__init__(parent=parent)
        self.db = db
        self.viewpoints: List[Viewpoint] = []
        self.row_to_object_map: List[Tuple[Viewpoint, ViewpointDescription]] = []
        self._last_loaded_project_id = None

        self.table_widget = None

        self.build_table()

    def showEvent(self, event: QEvent):
        """
        When the widget is shown, refresh its data to ensure it reflects the
        current application state.
        """
        current_project = self.db.get_current_project()
        if (
            current_project
            and current_project.project_id != self._last_loaded_project_id
        ):
            self.refresh_view()
        super().showEvent(event)

    def build_table(self):
        column_configs = [
            IndexColumnConfig(header="No", resizable=True),
            TextColumnConfig(
                header="Test viewpoint",
                is_pivot=True,
                default_width=0.20,
                editable=True,
            ),
            TextColumnConfig(
                header="Action Description",
                editable=True,
                default_width=0.35,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            TextColumnConfig(
                header="Error Message Expected",
                editable=True,
                default_width=0.25,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            TextColumnConfig(
                header="Expected Results",
                editable=True,
                default_width=0.20,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ),
            ActionColumnConfig(header="Actions"),
        ]
        column_configs[-1].widget_factory = self._create_custom_action_buttons

        self.model = TableModel(data=[])
        add_from_template_button = QPushButton("Add from templates")
        add_from_template_button.setObjectName("GreenButton")
        add_from_template_button.clicked.connect(self._on_add_from_template)
        self.table_widget = DataTableWidget(
            column_configs=column_configs,
            model=self.model,
            item_height=40,
            show_add_button=True,
            show_animated_add_row=True,
            custom_buttons=[add_from_template_button],
        )

        self.table_widget.delete_requested.connect(self._on_delete_row)
        self.table_widget.add_row_requested.connect(self._handle_add_row_to_group)
        self.table_widget.cell_changed.connect(self._on_cell_changed)
        self.table_widget.add_new_row_clicked.connect(
            self._handle_add_new_viewpoint_group
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table_widget)
        self.setLayout(layout)

    def _create_custom_action_buttons(self, data: Any, row_idx: int) -> QWidget:
        """Creates a custom widget containing "Save" and "Delete" buttons for the action column."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("GreenButton") 
        save_btn.clicked.connect(lambda: self._on_save_row_to_template(row_idx))
        
        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("RedButton")
        delete_btn.clicked.connect(lambda: self._on_delete_row(row_idx))

        layout.addWidget(save_btn)
        layout.addWidget(delete_btn)
        return container

    def refresh_view(self):
        """
        Refreshes the table with data for the currently active project.
        This is the primary method for loading and displaying data.
        """
        self.viewpoints = []
        self.row_to_object_map.clear()
        self.model.set_data([])

        current_project = self.db.get_current_project()
        if not current_project:
            logger.warning("No project selected. Page viewpoint table is empty.")
            self._last_loaded_project_id = None
            return

        logger.info(
            f"Loading page viewpoints for project: {current_project.project_id}"
        )
        all_viewpoints_data = self.db.get_viewpoints_sync(current_project.project_id)
        all_viewpoints = [
            Viewpoint.from_dict(vp_data) for vp_data in all_viewpoints_data
        ]
        # Filter for PAGE viewpoints
        self.viewpoints = [
            vp for vp in all_viewpoints if vp.viewpoint_type == ViewpointType.PAGE
        ]

        table_data = []
        for vp in self.viewpoints:
            if vp.viewpoint_details:
                for detail in vp.viewpoint_details:
                    row = [
                        None,
                        vp.name,
                        detail.description_input,
                        detail.error_message_expected,
                        detail.final_result_expected,
                        None,
                    ]
                    table_data.append(row)
                    self.row_to_object_map.append((vp, detail))
            else:
                row = [None, vp.name, "NULL", "NULL", "NULL", None]
                table_data.append(row)
                self.row_to_object_map.append((vp, None))
        self.model.set_data(table_data)
        self._last_loaded_project_id = current_project.project_id

    def _on_add_from_template(self):
        """
        Opens a dialog to select viewpoints from a template and add them.
        """
        current_project = self.db.get_current_project()
        if not current_project:
            logger.error("Cannot add viewpoint from template: No project is selected.")
            return

        dialog = AddFromTemplateDialog(self.db, ViewpointType.PAGE, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            viewpoints_to_add = dialog.get_selected_viewpoints()
            if not viewpoints_to_add:
                return

            logger.info(
                f"User chose to add {len(viewpoints_to_add)} viewpoint groups from template."
            )

            for vp_template in viewpoints_to_add:
                new_details_payload = [
                    {
                        "description_input": detail.description_input,
                        "error_message_expected": detail.error_message_expected,
                        "final_result_expected": detail.final_result_expected,
                    }
                    for detail in vp_template.viewpoint_details
                ]
                payload_to_create = {
                    "uuid": vp_template.viewpoint_id,
                    "name": vp_template.name,
                    "viewpoint_type": ViewpointType.PAGE.value,
                    "viewpoint_details": new_details_payload,
                    "project_id": current_project.project_id,
                }
                self.db.create_viewpoint_sync(payload_to_create)
            self.refresh_view()
    
    def _on_save_row_to_template(self, row_index: int):
        """Saves the viewpoint represented by the specified row to the template library."""
        if not (0 <= row_index < len(self.row_to_object_map)):
            return
        target_viewpoint, _ = self.row_to_object_map[row_index]

        row_data = self.model.get_row(row_index)
        if not row_data:
            return
        
        template_payload = {
            "uuid": target_viewpoint.viewpoint_id, 
            "name": row_data[1] or target_viewpoint.name,
            "viewpoint_type": ViewpointType.PAGE.value,
            "viewpoint_details": [
                {
                    "description_input": row_data[2] or "",
                    "error_message_expected": row_data[3] or "",
                    "final_result_expected": row_data[4] or "",
                }
            ]
        }
        success = self.db.save_or_update_template_sync(template_payload)
        if success:
            logger.info(f"Successfully saved row {row_index} as a new template.")
        else:
            logger.error(f"Failed to save row {row_index} as a template.")

    def _on_delete_row(self, row_index: int):
        if not (0 <= row_index < len(self.row_to_object_map)):
            logger.warning(f"Invalid row index for deletion: {row_index}")
            return
        viewpoint_to_modify, detail_to_remove = self.row_to_object_map[row_index]
        success = False
        if not detail_to_remove:
            logger.debug(
                f"Deleting the entire empty viewpoint group '{viewpoint_to_modify.name}'."
            )
            if viewpoint_to_modify.viewpoint_id:
                success = self.db.delete_viewpoint_sync(
                    viewpoint_to_modify.viewpoint_id
                )
            else:
                self.row_to_object_map.pop(row_index)
                self.model.remove_row(row_index)
                logger.info("Removed new, unsaved viewpoint group from UI.")
                return
        else:
            final_details_list = []
            for i, (vp_from_map, detail_from_map) in enumerate(self.row_to_object_map):
                if vp_from_map is viewpoint_to_modify:
                    if detail_from_map is detail_to_remove:
                        continue
                    if detail_from_map:
                        row_data = self.model.get_row(i)
                        if not row_data:
                            continue

                        detail_payload = {
                            "description_input": row_data[2] or "",
                            "error_message_expected": row_data[3] or "",
                            "final_result_expected": row_data[4] or "",
                        }
                        if detail_from_map.detail_id is not None:
                            detail_payload["action"] = "update"
                            detail_payload["detail_id"] = detail_from_map.detail_id
                        elif any(val.strip() for val in detail_payload.values()):
                            detail_payload["action"] = "create"
                        final_details_list.append(detail_payload)

            if not final_details_list:
                logger.debug(
                    f"Last detail removed. Deleting entire viewpoint '{viewpoint_to_modify.name}'."
                )
                success = self.db.delete_viewpoint_sync(
                    viewpoint_to_modify.viewpoint_id
                )
            else:
                bulk_update_payload = {"viewpoint_details": final_details_list}
                logger.debug(
                    f"Updating viewpoint '{viewpoint_to_modify.name}'"
                    f"after row deletion with payload: {bulk_update_payload}"
                )
                success = self.db.update_viewpoint_sync(
                    viewpoint_to_modify.viewpoint_id, bulk_update_payload
                )
        if success:
            logger.info(
                f"Successfully processed delete request for row {row_index}. Refreshing table."
            )
            self.refresh_view()
        else:
            logger.error(f"API call failed for row deletion {row_index}.")

    def _handle_add_new_viewpoint_group(self):
        if not self.db.get_current_project():
            logger.error("Cannot add new viewpoint group: No project is selected.")
            return

        logger.info("Adding a new local viewpoint group.")
        new_row_data = [None, "New Viewpoint Group", "", "", "", None]
        insert_position = self.model.get_row_count()

        self.table_widget.set_auto_edit_row(insert_position)
        self.model.add_row(insert_position, new_row_data)

        new_detail_placeholder = ViewpointDescription(
            description_input="",
            error_message_expected="",
            final_result_expected="",
            detail_id=None,
        )
        new_viewpoint_placeholder = Viewpoint(
            name="New Viewpoint Group",
            viewpoint_type=ViewpointType.PAGE,  # Correct type
            viewpoint_id=None,
            viewpoint_details=[new_detail_placeholder],
        )
        setattr(new_viewpoint_placeholder, "action", "create")
        self.row_to_object_map.insert(
            insert_position, (new_viewpoint_placeholder, new_detail_placeholder)
        )

    def _handle_add_row_to_group(self, row_context: RowContext):
        if not self.db.get_current_project():
            logger.error("Cannot add row to group: No project is selected.")
            return

        viewpoint_to_add_to, _ = self.row_to_object_map[row_context.data_index]
        if not viewpoint_to_add_to:
            return

        logger.debug(f"Adding a new local row after index {row_context.data_index}.")
        new_row_data = [None, viewpoint_to_add_to.name, "", "", "", None]
        insert_position = row_context.data_index + 1

        self.table_widget.set_auto_edit_row(insert_position)
        self.model.add_row(insert_position, new_row_data)

        new_detail_placeholder = ViewpointDescription(
            description_input="",
            error_message_expected="",
            final_result_expected="",
            detail_id=None,
        )
        setattr(new_detail_placeholder, "action", "create")
        self.row_to_object_map.insert(
            insert_position, (viewpoint_to_add_to, new_detail_placeholder)
        )

    def _on_cell_changed(self, abs_row_index: int, col_index: int, value: str):
        if not (0 <= abs_row_index < len(self.row_to_object_map)):
            logger.warning(f"Invalid row index for editing: {abs_row_index}")
            return

        current_project = self.db.get_current_project()
        if not current_project:
            logger.error("Cannot save changes: No project is selected.")
            self.refresh_view()
            return

        target_viewpoint, _ = self.row_to_object_map[abs_row_index]
        success = False

        if getattr(target_viewpoint, "action", None) == "create":
            new_row_data = self.model.get_row(abs_row_index)
            if not new_row_data:
                return

            target_viewpoint.name = new_row_data[1] or "Unnamed Viewpoint"
            first_detail = ViewpointDescription(
                description_input=new_row_data[2] or "",
                error_message_expected=new_row_data[3] or "",
                final_result_expected=new_row_data[4] or "",
                detail_id=None,
            )
            target_viewpoint.viewpoint_details = [first_detail]

            payload_to_create = target_viewpoint.to_dict()
            payload_to_create["project_id"] = current_project.project_id
            payload_to_create["viewpoint_type"] = ViewpointType.PAGE.value

            logger.debug(
                f"Attempting to CREATE viewpoint with payload: {payload_to_create}"
            )
            response = self.db.create_viewpoint_sync(payload_to_create)
            success = response is not None
            if not success:
                logger.warning(
                    f"Failed to create new viewpoint group. Removing placeholder row {abs_row_index}."
                )
                self.model.remove_row(abs_row_index)
                self.row_to_object_map.pop(abs_row_index)

        elif target_viewpoint and target_viewpoint.viewpoint_id is not None:
            edited_row_data = self.model.get_row(abs_row_index)
            if not edited_row_data:
                return

            new_name_from_ui = edited_row_data[1]

            final_details_list = []
            for i, (vp_from_map, detail_from_map) in enumerate(self.row_to_object_map):
                if vp_from_map is target_viewpoint:
                    row_data = self.model.get_row(i)
                    if not row_data:
                        continue

                    detail_payload = {
                        "description_input": row_data[2] or "null",
                        "error_message_expected": row_data[3] or "null",
                        "final_result_expected": row_data[4] or "null",
                    }
                    if detail_from_map and detail_from_map.detail_id is not None:
                        detail_payload["action"] = "update"
                        detail_payload["detail_id"] = detail_from_map.detail_id
                    elif any(val.strip() for val in detail_payload.values()):
                        detail_payload["action"] = "create"
                    final_details_list.append(detail_payload)

            bulk_update_payload = {
                "name": new_name_from_ui,
                "viewpoint_type": ViewpointType.PAGE.value,
                "viewpoint_details": final_details_list,
            }
            success = self.db.update_viewpoint_sync(
                target_viewpoint.viewpoint_id, bulk_update_payload
            )

        if success:
            logger.info("API call successful. Refreshing table to sync state.")
            self.refresh_view()
        else:
            logger.error("API call failed or was not executed.")
