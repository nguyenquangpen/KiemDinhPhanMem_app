import asyncio
import base64
from datetime import datetime
import gc
import json
import pickle  # nosec B403
from typing import Generic

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from cwagent.ais.browser.browser import Browser
from cwagent.ais.browser.context import BrowserContext, BrowserSession
from cwagent.ais.controller.models import ActionModel, ActionResult
from cwagent.ais.controller.views import Context, Controller
from services.logging_config import get_agent_logger
from settings.config import WS_ENDPOINT

logger = get_agent_logger()


class Agent(Generic[Context]):
    def __init__(
        self, browser: Browser | None = None, test_uuid: str = "", auth_token: str = "", test_context: dict = None, step_callback=None
    ):  # nosec B107
        self.auth_token = auth_token
        self.test_uuid = test_uuid
        self.ws_connect = None

        self.action_result = None
        self.is_done = False
        self.is_stopping = False

        self.current_step = 0
        self.step_callback = step_callback

        self.checkpoint_data = None
        self._run_finished_event = asyncio.Event()

        self.controller: Controller[Context] = Controller()

        self.browser = browser or Browser()
        self.browser_context = BrowserContext(
            browser=self.browser, config=self.browser.config.new_context_config
        )

        self.test_context = test_context or {}

        self.result_images = []
        logger.info(
            "[AGENT_INIT] Agent initialized | test_uuid=%s | has_browser=%s",
            self.test_uuid,
            browser is not None,
        )
    
    async def stop(self):
        logger.info("[AGENT_STOP] User requested stop. Sending signal to Server")
        self.is_stopping = True
        if self.ws_connect:
            try:
                await self.ws_connect.send(json.dumps({
                    "status": "cancelled",
                    "reason": "user clicked stop",
                }))
            # except ConnectionClosed:
            #     logger.warning("[AGENT_STOP] Connection closed while sending stop signal.")
            except Exception as e:
                logger.error(f"[AGENT_STOP_ERROR] Error sending stop signal: {e}", exc_info=True)

    async def run(self) -> None:
        logger.info("[AGENT_START] Starting Agent run | test_uuid=%s", self.test_uuid)

        # Establish WebSocket connection
        ws_url = f"{WS_ENDPOINT}/ws/agent_pool/{self.test_uuid}"
        logger.info("[WS_CONNECT] Connecting to WebSocket | url=%s", ws_url)
        self.ws_connect = await websockets.connect(
            ws_url,
            ping_interval=3000,
            ping_timeout=3000,
            additional_headers=[("Authorization", f"Bearer {self.auth_token}")],
            max_size=None,
        )
        logger.info("[WS_CONNECTED] WebSocket connection established")

        init_msg = {
            "type": "init",
            "payload": self.test_context,
        }
        logger.debug("[WS_SEND] Sending init message | data=%s", init_msg)
        await self.ws_connect.send(json.dumps(init_msg))

        while True:
            if self.is_stopping:
                logger.info("[WS_STOP] Stopping flag detected. Exiting loop.")
                break
            
            respone_raw = await self.ws_connect.recv()
            respone = json.loads(respone_raw)
            if respone.get("status", None) == "Done":
                logger.info("[WS_INIT] Server initialized successfully. Proceeding to RUN.")
                break
            else:
                logger.error("[WS_INIT_FAIL] Agent already existed on Server.")
                raise RuntimeError("Initialization failed: Agent session already exists (Status: Existed).")

        run_msg = {"type": "run"}
        logger.debug("[WS_SEND] Sending run message | data=%s", run_msg)
        await self.ws_connect.send(json.dumps(run_msg))

        try:
            logger.info("[WS_LOOP] Starting WebSocket message loop")
            while True:
                if self.is_stopping:
                    message_raw = await asyncio.wait_for(self.ws_connect.recv(), timeout=5)
                else:
                    message_raw = await self.ws_connect.recv()
                message = json.loads(message_raw)
                msg_type = message.get("type", "unknown")
                logger.info(
                    "[WS_RECV] Received message | type=%s | data=%s", msg_type, message
                )
                status = message.get("status", None)
                logger.info("[WS_STATUS] Processing message with status=%s", status)

                if "step_number" in message:
                    self.current_step = message["step_number"]
                    if self.step_callback:
                        self.step_callback(self.current_step)

                if status == "checkpoint":
                    logger.info("[CHECKPOINT] Processing checkpoint data from Server")
                    agent_state_b64 = message.get("agent_state")
                    page = await self.browser_context.get_current_page()
                    current_url = page.url
                    session_state = await self.browser_context.get_session_state()

                    self.checkpoint_data = {
                        "agent_state": agent_state_b64,
                        "session_state": session_state,
                        "current_url": current_url,
                        "step_number": self.current_step
                    }
                    if self.is_stopping:
                        break
                    continue
                
                if status == "restore_session":
                    session_data = message.get("data", {})
                    await self._handle_restore_session(session_data)
                    
                if status == "request_state":
                    logger.info("[STATE_REQ] Server requesting browser state")
                    state = await self.browser_context.get_state()
                    state_data: bytes = pickle.dumps(
                        state, protocol=pickle.HIGHEST_PROTOCOL
                    )
                    state_size = len(state_data)
                    logger.info(
                        "[STATE_SEND] Sending browser state | size_bytes=%d", state_size
                    )
                    try:
                        await self.ws_connect.send(state_data)
                    except websockets.exceptions.ConnectionClosedOK:
                        logger.warning("[STATE_SEND] Connection closed while sending state.")
                        continue

                if status == "server_actions":
                    actions_data = message.get("data", None)
                    action_count = len(actions_data) if actions_data else 0
                    logger.info(
                        "[ACTION_REQ] Server requesting actions execution | "
                        "action_count=%d | actions=%s",
                        action_count,
                        actions_data,
                    )
                    try:
                        await self.multi_act(actions_data)
                    except Exception as act_error:
                        logger.error(f"[MULTI_ACT_ERROR] Execution failed: {act_error}")
                        error_payload = {
                            "status": "execution_error",
                            "error": str(act_error),
                            "step_number": self.current_step
                        }
                        is_open = getattr(self.ws_connect, "open", False)
                        if self.ws_connect and is_open:
                            await self.ws_connect.send(json.dumps(error_payload))
                        continue 
   
                if status == "request_action_results":
                    result_count = len(self.action_result) if self.action_result else 0
                    logger.info(
                        "[RESULT_REQ] Server requesting action results | "
                        "result_count=%d | results=%s",
                        result_count,
                        self.action_result,
                    )
                    response_data = {"action_results": self.action_result}
                    logger.debug(
                        "[WS_SEND] Sending action results | data=%s", response_data
                    )
                    await self.ws_connect.send(json.dumps(response_data))

                if self.is_stopping:
                    logger.info("[WS_STOP] Stopping flag detected. Exiting loop.")
                    if state == "checkpoint":
                        logger.info("[WS_STOP] Checkpoint received during stop. Now exiting.")
                        break
                    else:
                        logger.info(f"[WS_STOP] Status was {status}, continuing to fetch final checkpoint...")
                        continue

                if status == "testcase_done":
                    logger.info("[TESTCASE_DONE] Server signaling test completion")
                    break

        except Exception as e:
            logger.error(
                "[AGENT_ERROR] Exception during agent run: %s", str(e), exc_info=True
            )
            is_open = getattr(self.ws_connect, "open", False)
            if self.ws_connect and not is_open:
                try:
                    last_gasp = {
                        "status": "agent_crash", 
                        "error": str(e),
                        "reason": "Exception in main loop"
                    }
                    await self.ws_connect.send(json.dumps(last_gasp))
                    logger.info("[AGENT_ERROR] Sent crash report to server.")
                except Exception as send_ex:
                    logger.warning(f"[AGENT_ERROR] Failed to send crash report: {send_ex}")
        
        finally:
            logger.info(
                "[AGENT_CLEANUP] Testcase run completed, closing WebSocket connection"
            )
            await self.ws_connect.close()
            await self.close()
            self._run_finished_event.set()

        logger.info(
            "[AGENT_END] Agent run completed | result_images_count=%d",
            len(self.result_images),
        )
        return self.result_images, self.action_result

    async def close(self):
        logger.info("[CLEANUP] Starting agent cleanup")
        if self.browser_context:
            logger.debug("[CLEANUP] Closing browser context")
            await self.browser_context.close()
        if self.browser:
            logger.debug("[CLEANUP] Closing browser")
            await self.browser.close()
        logger.debug("[CLEANUP] Running garbage collection")
        gc.collect()
        logger.info("[CLEANUP] Agent cleanup completed")

    async def multi_act(self, actions: list[ActionModel]) -> list[ActionResult]:
        results = []
        action_count = len(actions) if actions else 0
        logger.info(
            "[MULTI_ACT] Starting multi-action execution | action_count=%d",
            action_count,
        )

        await self.browser_context.remove_highlights()
        page = await self.browser_context.get_current_page()
        logger.debug("[MULTI_ACT] Browser context prepared, highlights removed")

        for i, action in enumerate(actions):
            if self.is_stopping:
                logger.warning("[MULTI_ACT_STOP] Agent is stopping, halting action execution")
                break
            logger.info(
                "[ACTION_EXEC] Executing action %d/%d | action_type=%s | data=%s",
                i + 1,
                action_count,
                getattr(action, "action_type", "unknown"),
                action,
            )

            action_status = await self.controller.act(action, self.browser_context)
            results.append(action_status.model_dump())

            logger.info(
                "[ACTION_RESULT] Action %d completed | success=%s | error=%s",
                i + 1,
                not action_status.error,
                action_status.error,
            )

            # Take screenshot after action
            raw = await page.screenshot(full_page=True, animations="disabled")
            screenshot_b64 = base64.b64encode(raw).decode("utf-8")
            self.result_images.append(screenshot_b64)
            logger.debug(
                "[SCREENSHOT] Screenshot captured after action %d | size_bytes=%d",
                i + 1,
                len(raw),
            )

            if action_status.is_done or action_status.error:
                logger.info(f"=-==-=-=-==-=-= stopping at action {i+1} =-==-=-=-==-=-=")
                logger.warning(
                    "[ACTION_STOP] ============ Stopping execution due to completion or error ============== | "
                    "is_done=%s | error=%s",
                    action_status.is_done,
                    action_status.error,
                )
                self.is_done = True
                # await self.close()
                break

        logger.info(
            "[MULTI_ACT] Multi-action execution completed | results_count=%d",
            len(results),
        )
        self.action_result = results
    
    async def _handle_restore_session(self, data: dict):
        """Handle restoring browser session from provided data."""
        logger.info("[DEBUG_RESTORE] Starting restore process...")
        current_url = data.get("current_url")
        session_state = data.get("session_state")

        if not session_state:
            logger.warning("[RESTORE_SESSION] No session state provided, skipping restore")
            return
        
        if self.browser_context.session:
            await self.browser_context.session.close()

        playwright_browser = await self.browser.get_playwright_browser()

        new_context = await playwright_browser.new_context(
            storage_state=session_state, 
            user_agent=self.browser_context.config.user_agent,
            no_viewport=True,
        )

        self.browser_context.session = BrowserSession(
            context=new_context,
        )
        page = await new_context.new_page()
        self.browser_context.active_tab = page

        logger.info("======-=-=-=-= _handle_restore_session =-=--=-= run to page url")
        await page.goto(current_url, wait_until="load", timeout=30000)
        await self.browser_context._wait_for_stable_network()
        
        self.action_result = [{"extracted_content": "Session restored and page loaded successfully", "include_in_memory": True}]
        self.is_done = False

