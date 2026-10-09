from services.api.base import BaseAPI
from services.api.utils import get_auth_headers, get_auth_params
from services.logging_config import get_api_logger
from models.data_classes import ViewpointType
from typing import Dict, Optional, Any

logger = get_api_logger()

class TemplateService(BaseAPI):
    async def create_templates(self, token, template_data: Dict[str, Any]) -> Dict[str, Any]:
        header = get_auth_headers(token)
        logger.debug('Creating template with data: %s', template_data)
        return await self.post(
            "api/templates", data=template_data, headers=header
        )
    
    async def get_template(self, token, template_id):
        headers = get_auth_headers(token)
        return await self.get(
            f"api/templates/{template_id}", headers=headers
        )
    
    async def list_templates(self, token, viewpoint_type: Optional[ViewpointType] = None) -> Dict[str, Any]:        
        headers = get_auth_headers(token)
        params = get_auth_params()

        if viewpoint_type:
            params['viewpoint_type'] = viewpoint_type.value
            logger.debug(f"Requesting templates with filter: viewpoint_type={viewpoint_type.value}")
        else:
            logger.debug("Requesting all templates")
            
        return await self.get("api/templates/", headers=headers, params=params)

    async def update_templates(self, token, template_id, template_data):
        header = get_auth_headers(token)
        logger.debug(
            "Updating template with ID: %s and data: %s",
            template_id,
            template_data,
        )
        return await self.patch(
            f"api/templates/{template_id}",
            data=template_data,
            headers=header
        )
    
    async def delete_templates(self, token, template_id):
        header = get_auth_headers(token)
        logger.debug("Deleting templates with ID: %s", template_id)
        return await self.delete(f"api/templates/{template_id}", headers=header)

    async def clone_templates(self, token, template_data: Dict[str, Any]) -> Dict[str, Any]:
        header = get_auth_headers(token)
        logger.debug(
            "Cloning template with data=%s", template_data
        )
        return await self.post(
            "api/templates/clone",
            headers=header
        )
    