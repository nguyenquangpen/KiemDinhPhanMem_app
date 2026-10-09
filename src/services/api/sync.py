from typing import List, Any, Dict
from services.api.base import BaseAPI
from services.api.utils import get_auth_headers, get_auth_params
from services.logging_config import get_api_logger

logger = get_api_logger()

class SyncService(BaseAPI):
    def __init__(self, endpoint):
        super().__init__(endpoint)

    async def push_sync_data(self, token: str, logs: List[Dict[str, Any]]):
        headers = get_auth_headers(token)
        return await self.post("api/sync/push", data={"logs":logs}, headers=headers, return_status=True)

    async def get_snapshot(self, token: str):
        headers = get_auth_headers(token)
        return await self.get("api/sync/snapshot", headers=headers)
    
    async def pull_sync_data(self, token: str, since: str = None):
        headers = get_auth_headers(token)
        params = {}
        if since:
            params["since"] = since
        return await self.get("api/sync/pull", headers=headers, params=params)