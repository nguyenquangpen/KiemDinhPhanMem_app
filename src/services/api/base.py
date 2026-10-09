# Base API class for handling API requests and responses.
import httpx

from services.logging_config import get_api_logger
import json

logger = get_api_logger()


class BaseAPI:
    """
    Base API class for handling API requests and responses.
    """

    def __init__(self, endpoint):
        self.endpoint = endpoint
        logger.info("Initialized API client for endpoint: %s", endpoint)

    async def get(self, path, params=None, headers=None):
        """
        Perform an asynchronous GET request to the API.
        Args:
            path (str): The API endpoint path.
            params (dict, optional): Query parameters for the request.
            headers (dict, optional): Headers to include in the request.
        """
        url = f"{self.endpoint}/{path}"
        logger.debug("Making GET request to: %s", url)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=100,
                )
                response.raise_for_status()
                logger.debug(
                    "GET request successful: %s (status: %d)", url, response.status_code
                )
                return response.json()
            except httpx.HTTPError as e:
                logger.error("Error during GET request to %s: %s", url, e)
                return None

    async def post(self, path, data=None, headers=None, return_status = False):
        """
        Perform an asynchronous POST request to the API.

        Args:
            path (str): The API endpoint path.
            data (dict, optional): The JSON payload to include in the request.
            headers (dict, optional): Headers to include in the request.

        Returns:
            dict: The JSON response from the API or None if an error occurred.
        """
        url = f"{self.endpoint}/{path}"
        logger.debug("Making POST request to: %s", url)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url, json=data, headers=headers, timeout=100
                )
                response.raise_for_status()
                logger.debug(
                    "POST request successful: %s (status: %d)",
                    url,
                    response.status_code,
                )
                if return_status: return response.json(), response.status_code
                return response.json()
            except httpx.HTTPError as e:
                logger.error("Error during POST request to %s: %s", url, e)
                if return_status: return None, response.status_code
                return None

    async def put(self, path, data=None, headers=None):
        """
        Perform an asynchronous PUT request to the API.

        Args:
            path (str): The API endpoint path.
            data (dict, optional): The JSON payload to include in the request.
            headers (dict, optional): Headers to include in the request.

        Returns:
            dict: The JSON response from the API or None if an error occurred.
        """
        url = f"{self.endpoint}/{path}"
        logger.debug("Making PUT request to: %s", url)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    url, json=data, headers=headers, timeout=100
                )
                response.raise_for_status()
                logger.debug(
                    "PUT request successful: %s (status: %d)", url, response.status_code
                )
                return response.json()
            except httpx.HTTPError as e:
                logger.error("Error during PUT request to %s: %s", url, e)
                return None

    async def delete(self, path, headers=None):
        """
        Perform an asynchronous DELETE request to the API.

        Args:
            path (str): The API endpoint path.
            headers (dict, optional): Headers to include in the request.

        Returns:
            dict: The JSON response from the API or None if an error occurred.
        """
        url = f"{self.endpoint}/{path}"
        logger.debug("Making DELETE request to: %s", url)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(url, headers=headers, timeout=100)
                response.raise_for_status()
                logger.debug(
                    "DELETE request successful: %s (status: %d)",
                    url,
                    response.status_code,
                )
                return response.json()
            except httpx.HTTPError as e:
                logger.error("Error during DELETE request to %s: %s", url, e)
                return None

    async def patch(self, path, data=None, headers=None):
        """
        Perform an asynchronous PATCH request to the API.

        Args:
            path (str): The API endpoint path.
            data (dict, optional): The JSON payload to include in the request.
            headers (dict, optional): Headers to include in the request.

        Returns:
            dict: The JSON response from the API or None if an error occurred.
        """
        url = f"{self.endpoint}/{path}"
        logger.debug("Making PATCH request to: %s", url)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.patch(
                    url, json=data, headers=headers, timeout=100
                )
                response.raise_for_status()
                logger.debug(
                    "PATCH request successful: %s (status: %d)",
                    url,
                    response.status_code,
                )
                return response.json()
            except httpx.HTTPError as e:
                logger.error("Error during PATCH request to %s: %s", url, e)
                return None
