# utility functions for API services
from ..logging_config import get_api_logger

logger = get_api_logger()


class APIError(Exception):
    """Base exception for API-related errors."""


class UnauthorizedError(APIError):
    """Raised when API returns 401 status."""


class NotFoundError(APIError):
    """Raised when API returns 404 status."""


class ServerError(APIError):
    """Raised when API returns 5xx status."""


class InvalidResponseError(APIError):
    """Raised when API response is invalid or malformed."""


def get_auth_headers(token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_auth_params():
    return {
        # "include_docs": "true"
    }


def handle_api_error(response):
    if response.status_code == 401:
        raise UnauthorizedError("Unauthorized access - invalid token")
    elif response.status_code == 404:
        raise NotFoundError("Resource not found")
    elif response.status_code >= 500:
        raise ServerError("Server error - please try again later")
    else:
        response.raise_for_status()  # Raise for other HTTP errors


def parse_json_response(response):
    try:
        return response.json()
    except ValueError as exc:
        raise InvalidResponseError("Invalid JSON response") from exc


def format_api_url(endpoint, path):
    return f"{endpoint}/{path}"


def log_api_request(method, url, headers=None, params=None, data=None):
    log_message = "Request: %s %s"
    logger.debug(log_message, method, url)

    if headers:
        # Don't log sensitive authorization headers
        safe_headers = {
            k: v for k, v in headers.items() if k.lower() != "authorization"
        }
        if "authorization" in [k.lower() for k in headers.keys()]:
            safe_headers["authorization"] = (
                "[REDACTED]"  # nosec B105 # Security redaction
            )
        logger.debug("Request headers: %s", safe_headers)

    if params:
        logger.debug("Request params: %s", params)
    if data:
        logger.debug("Request data: %s", data)


def log_api_response(response):
    logger.debug("Response: %s %s", response.status_code, response.reason)

    try:
        response_body = response.json()
        # Don't log sensitive response data
        if isinstance(response_body, dict) and "token" in response_body:
            safe_body = response_body.copy()
            safe_body["token"] = (  # nosec B105
                "[REDACTED]"  # nosec B105 # Security redaction for logs
            )
            logger.debug("Response body: %s", safe_body)
        else:
            logger.debug("Response body: %s", response_body)
    except ValueError:
        logger.debug("Response body: Not JSON or empty")


def validate_response(response):
    if not response.ok:
        log_api_response(response)
        handle_api_error(response)
    return parse_json_response(response)
