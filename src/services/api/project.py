# project service for managing projects and tasks
from services.api.base import BaseAPI
from services.api.utils import get_auth_headers, get_auth_params
from services.logging_config import get_api_logger

logger = get_api_logger()


class ProjectService(BaseAPI):
    def __init__(self, endpoint):
        super().__init__(endpoint)

    async def create_project(self, token, project_data, return_status):
        headers = get_auth_headers(token)
        logger.debug("Creating project with data: %s", project_data)
        return await self.post("api/projects", data=project_data, headers=headers, return_status=return_status)

    async def get_project(self, token, project_id):
        headers = get_auth_headers(token)
        logger.debug("Fetching project with ID: %s", project_id)
        return await self.get(f"api/projects/{project_id}", headers=headers)

    async def patch_update_project(self, token, project_id, project_data):
        """Update an existing project.

        Args:
            token (_type_): _description_
            project_id (_type_): _description_
            project_data (_type_): _description_

        Returns:
            _type_: _description_
        """
        headers = get_auth_headers(token)
        logger.debug(
            "Updating project with ID: %s and data: %s", project_id, project_data
        )
        return await self.patch(
            f"api/projects/{project_id}",
            data=project_data,
            headers=headers,
        )

    async def delete_project(self, token, project_id):
        headers = get_auth_headers(token)
        logger.debug("Deleting project with ID: %s", project_id)
        return await self.delete(f"api/projects/{project_id}", headers=headers)

    async def list_projects(self, token):
        headers = get_auth_headers(token)
        logger.debug("Listing projects")
        return await self.get("api/projects", params=get_auth_params(), headers=headers)
