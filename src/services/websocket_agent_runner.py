"""
Enhanced Agent Test Runner with WebSocket Communication Support

This service provides execution and remote WebSocket communication
for distributed test case execution between local browser and remote server.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import websockets
from websockets import WebSocketClientProtocol

from cwagent.ais.agent_run import Agent
from cwagent.ais.browser.browser import Browser, BrowserConfig
from services.api.utils import get_auth_headers
from services.api.viewpoints import ViewpointsService
from services.logging_config import get_logger
from settings.config import WS_ENDPOINT

logger = get_logger("enhanced_agent_runner")


class EnhancedAgentTestRunner:
    """Enhanced agent test runner with WebSocket communication support"""

    def __init__(
        self,
        headless: bool = True,
        use_websocket: bool = True,
        websocket_url: str = WS_ENDPOINT,
        auth_token: str = "",  # nosec B107
        project_id: uuid.UUID = None,
    ):
        self.headless = headless
        self.use_websocket = use_websocket
        self.websocket_url = websocket_url
        self.auth_token = auth_token
        self.project_id = project_id
        self.browser_config = BrowserConfig(
            headless=headless,
            disable_security=True,
            deterministic_rendering=True,
        )
        # Internal state
        self.agent: Optional[Agent] = None
        self.is_running = False
        self._viewpoints_service: Optional[ViewpointsService] = None

    async def initialize(self, test_uuid: str = "local", test_context: Dict = None, on_step_update = None):
        """Initialize the agent and browser"""
        try:
            logger.info("Initializing enhanced agent test runner")
            logger.info("Mode: %s", "WebSocket" if self.use_websocket else "Local")

            # Create browser with our config
            browser = Browser(self.browser_config)

            # Create agent with WebSocket configuration
            self.agent = Agent(
                browser=browser, test_uuid=test_uuid, auth_token=self.auth_token, test_context=test_context, step_callback=on_step_update
            )

            # For local mode, the agent/browser manages initialization internally

            logger.info("Enhanced agent test runner initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize enhanced agent test runner: %s", str(e))
            raise

    def _build_ws_url(self) -> str:
        base = (self.websocket_url or "").rstrip("/")
        return f"{base}/ws/agent_pool/{self.agent.test_uuid}"

    # NEW: helper to build consistent headers (reuse existing auth header util)
    def _build_ws_headers(self) -> Dict[str, str]:
        # get_auth_headers handles token formatting consistently across app
        headers = get_auth_headers(self.auth_token) if self.auth_token else {}
        if not headers:
            logger.warning("No auth token provided for WebSocket connection")
        return headers

    # NEW: robust retrying connector to mitigate handshake timeouts
    async def _connect_with_retry(
        self,
        ws_url: str,
        headers: Dict[str, str],
        retries: int = 3,
        open_timeout: float = 20.0,
        close_timeout: float = 10.0,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
        initial_backoff: float = 1.0,
        backoff_factor: float = 2.0,
    ) -> WebSocketClientProtocol:
        """
        Attempt to open a WebSocket connection with retries and exponential backoff.
        """
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt <= retries:
            try:
                logger.info(
                    "Opening WebSocket (%s), attempt %d/%d",
                    ws_url,
                    attempt + 1,
                    retries + 1,
                )
                return await websockets.connect(
                    ws_url,
                    open_timeout=open_timeout,
                    close_timeout=close_timeout,
                    ping_interval=ping_interval,
                    ping_timeout=ping_timeout,
                    additional_headers=headers,
                    max_queue=None,  # do not drop messages under load
                    max_size=None,  # allow large inbound messages
                )
            except asyncio.TimeoutError as e:
                last_exc = e
                logger.warning(
                    "WebSocket handshake timed out (attempt %d/%d): %s",
                    attempt + 1,
                    retries + 1,
                    str(e),
                )
            except Exception as e:
                # Auth/routing errors may expose status_code; handle specifically
                last_exc = e
                status = getattr(e, "status_code", None)
                if status in (401, 403, 404):
                    logger.error(
                        "WebSocket handshake HTTP %s, not retrying (auth/routing)",
                        status,
                    )
                    break
                logger.warning(
                    "WebSocket connection error (attempt %d/%d): %s",
                    attempt + 1,
                    retries + 1,
                    str(e),
                )

            # backoff before next try
            if attempt == retries:
                break
            sleep_for = initial_backoff * (backoff_factor**attempt)
            await asyncio.sleep(sleep_for)
            attempt += 1

        assert last_exc is not None  # nosec B101
        raise RuntimeError(f"Failed to open WebSocket after retries: {last_exc}")

    async def run_agent_with_test_case(self) -> List[str]:
        """Run agent with WebSocket communication for specfific test case"""
        if not self.agent:
            raise RuntimeError("Agent not initialized")
        return await self.agent.run()

    async def cleanup(self):
        """Clean up agent resources"""
        logger.info("Cleanup initiated for EnhancedAgentTestRunner.")
        try:
            if self.agent:
                await self.agent.close()
            logger.info("Enhanced agent test runner cleaned up successfully")
        except Exception as e:
            logger.error("Error during enhanced agent cleanup: %s", str(e))

    async def execute_test_cases_websocket(self, test_cases: List[Dict]) -> List[Dict]:
        """Execute test cases using WebSocket communication with remote server"""
        results = []

        for test_case in test_cases:
            logger.info(
                "Executing test case via WebSocket: %s",
                test_case.get("test_case", "Unknown"),
            )

            result = await self.execute_single_test_case_websocket(test_case)
            results.append(result)

        return results

    async def execute_single_test_case_websocket(self, test_data: Dict, on_step_update = None) -> Dict:
        """Execute a single test case using WebSocket communication"""
        test_case_info = test_data.get("test_case", {})
        test_id = test_case_info.get("uuid")
        test_name = test_case_info.get("test_case", "Unknown Test Case")

        result = {
            "test_id": test_id,
            "test_name": test_name,
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "screenshots": [],
            "errors": [],
            "websocket_communication": True,
            "checkpoint_data": None,
            "step_number": 0,
        }

        try:
            # Create a custom WebSocket-enabled agent for this test case
            await self.initialize(test_uuid=test_id, test_context=test_data, on_step_update=on_step_update)

            # Override the agent's run method to handle our custom test case
            result_images, action_result = await self.run_agent_with_test_case()
            if self.agent:
                result["step_number"] = self.agent.current_step

            result["screenshots"] = result_images
            result["action_result"] = action_result
            result["end_time"] = datetime.now().isoformat()

            if self.agent and self.agent.is_stopping:
                result["status"] = "cancelled"
                result["error"] = "User stopped execution"
            elif action_result:
                result["status"] = "passed"
            else:
                result["status"] = "failed"
            
            # Retrieve checkpoint data if available
            if self.agent and hasattr(self.agent, 'checkpoint_data'):
                result["checkpoint_data"] = self.agent.checkpoint_data
                logger.info(
                    "Retrieved checkpoint data from Agent for test case '%s': %s", 
                    test_name, 
                    "Found" if self.agent.checkpoint_data else "None"
                )
            logger.info("WebSocket test case '%s' completed successfully", test_name)

        except Exception as e:
            if self.agent and self.agent.is_stopping:
                result["status"] = "cancelled"
                result["error"] = "User stopped execution"
            else:
                error_msg = f"WebSocket test execution failed: {str(e)}"
                result["status"] = "error"
                result["error"] = error_msg
                result["errors"] = [error_msg]
            result["end_time"] = datetime.now().isoformat()
            logger.error("WebSocket test case '%s' failed: %s", test_name, str(e))
        return result
    
    async def graceful_stop(self):
        """Gracefully stop the agent execution"""
        logger.info("Gracefully stopping the EnhancedAgentTestRunner.")
        if self.agent:
            await self.agent.stop()
            
class EnhancedAgentTestRunnerService:
    """Enhanced service wrapper supporting both WebSocket and local execution"""

    def __init__(
        self,
        headless: bool = True,
        use_websocket: bool = True,
        websocket_url: str = WS_ENDPOINT,
        auth_token: str = "",  # nosec B107
        project_id: uuid.UUID = None,
    ):
        self.runner = EnhancedAgentTestRunner(
            headless=headless,
            use_websocket=use_websocket,
            websocket_url=websocket_url,
            auth_token=auth_token,
            project_id=project_id,
        )
        self.headless = headless
        self.use_websocket = use_websocket

    async def execute_test_cases(self, test_cases: List[Dict]) -> List[Dict]:
        """Execute test cases using configured mode WebSocket"""
        try:
            logger.info("Executing test cases via WebSocket communication")
            return await self.runner.execute_test_cases_websocket(test_cases)
        finally:
            await self.runner.cleanup()

    async def execute_single_test(self, test_case: Dict, on_step_update = None) -> Dict:
        """Execute a single test case using configured mode"""
        try:
            try:
                return await self.runner.execute_single_test_case_websocket(test_case, on_step_update=on_step_update)
            except Exception as e:
                logger.error("Error executing single test: %s", str(e))
                return {
                    "test_id": test_case.get("uuid", "unknown"),
                    "test_name": test_case.get("test_case", "Unknown"),
                    "status": "error",
                    "error": str(e),
                    "start_time": datetime.now().isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "websocket_communication": self.use_websocket,
                }
        finally:
            logger.info("Ensuring runner is cleaned up for test: %s", test_case.get("test_case", "Unknown"))
            await self.runner.cleanup()
    
    async def stop_execution(self):
        """Stops the current test execution by cleaning up the runner."""
        logger.info("Received stop signal. Cleaning up the agent runner.")
        if self.runner:
            await self.runner.graceful_stop()


# Alias for backward compatibility
WebSocketAgentTestRunner = EnhancedAgentTestRunnerService
