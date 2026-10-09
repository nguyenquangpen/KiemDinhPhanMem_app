# auth service for handling user authentication and authorization
from services.api.base import BaseAPI
from services.api.utils import get_auth_headers
from services.logging_config import get_api_logger

logger = get_api_logger()


class AuthService(BaseAPI):
    """Service for handling user authentication and authorization."""

    async def login(self, username, password):
        logger.info("Attempting login for user: %s", username)
        headers = get_auth_headers()
        data = {"username": username, "password": password}
        result = await self.post(
            "auth/login",
            data=data,
            headers=headers,
        )
        if result:
            logger.info("Login successful for user: %s", username)
        else:
            logger.warning("Login failed for user: %s - %s", username, password)
        return result
    
    async def logout(self, token):
        logger.info("Logging out user")
        headers = get_auth_headers(token)
        result = await self.post("auth/logout", headers=headers)
        if result:
            logger.info("Logout successful")
        else:
            logger.warning("Logout failed")
        return result

    # register a new user
    async def register(self, username, password):
        logger.info("Attempting to register new user: %s", username)
        headers = get_auth_headers()
        data = {"username": username, "password": password}
        result = await self.post("auth/register", data=data, headers=headers)
        if result:
            logger.info("Registration successful for user: %s", username)
        else:
            logger.warning("Registration failed for user: %s", username)
        return result

    async def get_user_info(self, token):
        logger.debug("Fetching user info")
        headers = get_auth_headers(token)
        result = await self.get("auth/me", headers=headers)
        if result:
            logger.debug("User info retrieved successfully")
        else:
            logger.warning("Failed to retrieve user info")
        return result
    
class CwAuthService(BaseAPI):

    async def CWlogin(self, email, password):
        logger.info("Attempting login to cw for user: %s", email)
        data = {"email": email, "password": password}
        result = await self.post("api/v1/auth/login", data=data)
        if result and result.get("success"):
            logger.info("Co-well API login successful for user: %s", email)
        else:
            logger.warning("Co-well API login failed for user: %s", email)
        return result
