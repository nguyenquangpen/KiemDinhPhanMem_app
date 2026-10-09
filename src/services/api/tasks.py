from services.api.base import BaseAPI
from services.api.utils import get_auth_headers
from services.logging_config import get_api_logger

logger = get_api_logger()


class TaskService(BaseAPI):
    """Service for managing tasks.
    Endpoints convention follows TestCaseService style:
    - List:   GET  /api/tasks/by_project?project_id={id}
    - Create: POST /api/tasks
    - Get:    GET  /api/tasks/{id}
    - Update: PUT  /api/tasks/{id}
    - Delete: DELETE /api/tasks/{id}
    """

    async def list_tasks(self, token: str, project_id: str):
        headers = get_auth_headers(token)
        logger.debug("Listing tasks for project: %s", project_id)
        return await self.get(
            "api/tasks/by_project", params={"project_id": project_id}, headers=headers
        )

    async def create_task(self, token: str, task_data: dict, project_id: str):
        headers = get_auth_headers(token)
        data = task_data.copy()
        data["project_id"] = project_id  # Ensure project_id is included in task data
        logger.debug("Creating task for project %s, data: %s", project_id, data)
        res = await self.post(
            "api/tasks",
            data=data,
            headers=headers,
        )
        logger.debug("Created task %s, data: %s", res, data)
        return res

    async def get_task(self, token: str, task_id: str):
        headers = get_auth_headers(token)
        logger.debug("Fetching task with ID: %s", task_id)
        return await self.get(f"api/tasks/{task_id}", headers=headers)

    async def update_task(self, token: str, task_id: str, task_data: dict):
        headers = get_auth_headers(token)
        logger.debug("Updating task %s with data: %s", task_id, task_data)
        return await self.put(f"api/tasks/{task_id}", data=task_data, headers=headers)

    async def delete_task(self, token: str, task_id: str):
        headers = get_auth_headers(token)
        logger.debug("Deleting task with ID: %s", task_id)
        return await self.delete(f"api/tasks/{task_id}", headers=headers)

    async def generate_testcases(self, token: str, task_id: str, payload: dict):
        """Generate testcases for a task."""
        headers = get_auth_headers(token)
        logger.debug("Generating testcases for task %s with options: %s", task_id, payload)
        return await self.post(
            f"api/tasks/{task_id}/generate-testcases", data=payload, headers=headers
        )

    async def get_generation_status(self, token: str, task_id: str):
        """Get testcase generation status for a task."""
        headers = get_auth_headers(token)
        logger.debug("Getting generation status for task: %s", task_id)
        return await self.get(f"api/tasks/{task_id}/generation-status", headers=headers)

    async def get_background_task_status(self, token: str, celery_task_id: str):
        """Get background task status from Celery."""
        headers = get_auth_headers(token)
        logger.debug("Getting background task status for: %s", celery_task_id)
        return await self.get(
            f"api/background-tasks/{celery_task_id}/status", headers=headers
        )
