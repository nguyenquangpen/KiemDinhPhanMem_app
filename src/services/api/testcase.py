from services.api.base import BaseAPI
from services.api.utils import get_auth_headers
from services.logging_config import get_api_logger

logger = get_api_logger()


class TestCaseService(BaseAPI):
    """Service for managing test cases.
    - testcases:
      - `POST /testcases/?{project_id}` - Create a new test case
      - `GET /testcases/?{project_id}` - Get test cases of a project

        Args:
            BaseAPI (_type_): _description_
    """

    async def create_test_case(self, token, test_case_data, project_id):
        """Create a new test case."""
        headers = get_auth_headers(token)
        logger.debug("Creating test case with data: %s", test_case_data)
        return await self.post(
            f"api/testcases?project_id={project_id}",
            data=test_case_data,
            headers=headers,
        )

    async def get_test_cases(self, token, project_id, task_id=None):
        """Get test cases of a project."""
        headers = get_auth_headers(token)
        params = {"project_id": project_id}
        if task_id:
            params["task_id"] = task_id
        logger.debug("Fetching test cases for project ID: %s", project_id)
        return await self.get("api/testcases", params=params, headers=headers)

    # async def get_test_case(self, token, test_case_id):
    #     """Get details of a specific test case."""
    #     headers = get_auth_headers(token)
    #     logger.debug("Fetching test case with ID: %s", test_case_id)
    #     return await self.get(f"api/testcases/{test_case_id}", headers=headers)

    async def update_test_case(self, token, test_case_id, test_case_data):
        """Update details of a specific test case."""
        headers = get_auth_headers(token)
        logger.debug(
            "Updating test case with ID: %s and data: %s", test_case_id, test_case_data
        )
        return await self.put(
            f"api/testcases/{test_case_id}", data=test_case_data, headers=headers
        )

    async def delete_test_case(self, token, test_case_id):
        """Delete a specific test case."""
        headers = get_auth_headers(token)
        logger.debug("Deleting test case with ID: %s", test_case_id)
        return await self.delete(f"api/testcases/{test_case_id}", headers=headers)
