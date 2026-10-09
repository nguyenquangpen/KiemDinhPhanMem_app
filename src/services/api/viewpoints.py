# viewpoints service for managing function viewpoints and component viewpoints
from services.api.base import BaseAPI
from services.api.utils import get_auth_headers, get_auth_params
from services.logging_config import get_api_logger

logger = get_api_logger()


class ViewpointsService(BaseAPI):
    async def create_viewpoint(self, token, function_viewpoint_data):
        headers = get_auth_headers(token)
        logger.debug("Creating viewpoint with data: %s", function_viewpoint_data)
        return await self.post(
            "api/viewpoints", data=function_viewpoint_data, headers=headers
        )

    async def get_viewpoint(self, token, viewpoint_id):
        headers = get_auth_headers(token)
        return await self.get(f"api/viewpoints/{viewpoint_id}", headers=headers)

    async def update_viewpoint(self, token, viewpoint_id, function_viewpoint_data):
        headers = get_auth_headers(token)
        logger.debug(
            "Updating viewpoint with ID: %s and data: %s",
            viewpoint_id,
            function_viewpoint_data,
        )
        return await self.patch(
            f"api/viewpoints/{viewpoint_id}/bulk-update",
            data=function_viewpoint_data,
            headers=headers,
        )

    async def delete_viewpoint(self, token, viewpoint_id):
        headers = get_auth_headers(token)
        logger.debug("Deleting viewpoint with ID: %s", viewpoint_id)
        return await self.delete(f"api/viewpoints/{viewpoint_id}", headers=headers)

    async def list_viewpoints(self, token, project_id: str):
        headers = get_auth_headers(token)
        
        params = get_auth_params()
        params["project_id"] = project_id

        logger.debug("Listing viewpoints")
        return await self.get(
            "api/viewpoints", headers=headers, params=params
        )

    async def get_viewpoint_choices(self, token):
        headers = get_auth_headers(token)
        logger.debug("Fetching viewpoint choices")
        return await self.get(
            "api/vp_choices",
            params=get_auth_params(),
            headers=headers,
        )
