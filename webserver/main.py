# webserver/main.py
import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse  # To serve index.html from root
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

# Import our assessment engine class
from assessment_engine.engine import AssessmentSession

# Import the Pydantic models we created
from .models import (
    ActionCompleteMessage,
    BaseMessage,
    DrawStrokeMessage,
    SubmitTextResponseMessage,
)

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)  # Use a named logger
app = FastAPI()

# --- Static Files Setup ---
# Serve files from 'static' dir located one level above this file's directory
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- WebSocket Logic ---

# Dictionary to hold active assessment sessions
active_sessions: dict[WebSocket, AssessmentSession] = {}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    log.info(f"WebSocket connection accepted from {websocket.client}.")
    session: Optional[AssessmentSession] = None  # Initialize session variable

    try:
        while True:
            # Wait for a message (expecting JSON)
            try:
                raw_data = await websocket.receive_json()
                log.info(f"Received raw data: {raw_data}")

                # --- Pydantic Validation ---
                try:
                    # 1. Parse into BaseMessage to safely get type/common fields
                    base_msg = BaseMessage.parse_obj(raw_data)
                    log.info(f"Parsed base message type: {base_msg.type}")

                    # 2. Parse into specific model for full validation
                    # We store the fully validated Pydantic object
                    validated_data: BaseMessage  # Type hint for clarity

                    if base_msg.type == "draw_stroke":
                        validated_data = DrawStrokeMessage.parse_obj(raw_data)
                        log.info("Validated as DrawStrokeMessage.")
                    elif base_msg.type == "action_complete":
                        validated_data = ActionCompleteMessage.parse_obj(
                            raw_data
                        )
                        log.info("Validated as ActionCompleteMessage.")
                    elif base_msg.type == "submit_text_response":
                        validated_data = SubmitTextResponseMessage.parse_obj(
                            raw_data
                        )
                        log.info("Validated as SubmitTextResponseMessage.")
                    else:
                        # Should not be reachable via Literal type hint
                        log.warning(
                            f"Unknown message type '{base_msg.type}' "
                            f"received after base parsing."
                        )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"Unknown message type: {base_msg.type}",
                            }
                        )
                        continue  # Skip processing

                except ValidationError as e:
                    log.error(
                        f"Validation failed for data: {raw_data}\n"
                        f"Error: {e.json(indent=2)}"
                    )
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Invalid message format received.",
                            # Optional: "details": json.loads(e.json()),
                        }
                    )
                    continue  # Skip processing

                # --- Session Management (Create on first valid message) ---
                if session is None:
                    try:
                        # Hardcode '6x8' task for now
                        task_id_to_use = "6x8"
                        session = AssessmentSession(task_id=task_id_to_use)
                        active_sessions[websocket] = session
                        log.info(
                            f"Created AssessmentSession for task '{task_id_to_use}' "
                            f"for {websocket.client}. "
                            f"Total sessions: {len(active_sessions)}"
                        )
                    except ValueError as e:
                        log.error(
                            f"Failed to create session for task '{task_id_to_use}': {e}"
                        )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"Failed to load task rules for '{task_id_to_use}'.",
                            }
                        )
                        break  # Close if session fails init
                    except Exception as e:
                        log.error(
                            f"Unexpected error creating session task '{task_id_to_use}': {e}",
                            exc_info=True,
                        )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Internal server error during session creation.",
                            }
                        )
                        break

                # --- Process Event through Engine ---
                if session:
                    try:
                        action = session.process_event(validated_data)

                        if action:
                            await websocket.send_json(action)
                            log.info(f"Action sent: {action}")

                        if session.assessment_complete:
                            log.info(
                                f"Assessment complete flag set for session "
                                f"with {websocket.client}."
                            )
                            # Option: break here?

                    except Exception as e:
                        log.error(
                            f"Error processing event in engine: {e}",
                            exc_info=True,
                        )
                        await websocket.send_json(
                            {"type": "error", "message": "Error processing event."}
                        )
                        # Option: break here?

            except WebSocketDisconnect:
                log.info(f"WebSocket disconnected by client: {websocket.client}")
                break
            except json.JSONDecodeError:
                log.warning(
                    f"Received non-JSON message from {websocket.client}, ignoring."
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid data format. Please send JSON.",
                    }
                )
            except Exception as e:
                log.error(
                    f"Error during WebSocket loop for {websocket.client}: {e}",
                    exc_info=True,
                )
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "An internal server error occurred.",
                        }
                    )
                except Exception:
                    log.error("Failed to send error msg before closing.")
                break

    except Exception as e:
        log.error(
            f"Unexpected WebSocket error for {websocket.client}: {e}",
            exc_info=True,
        )

    finally:
        # --- Cleanup ---
        log.info(f"Cleaning up connection for {websocket.client}")
        if websocket in active_sessions:
            del active_sessions[websocket]
            log.info(f"Removed session. Total sessions: {len(active_sessions)}")
        else:
            log.warning(
                "WebSocket not found in active sessions during cleanup "
                "(might have failed before session creation)."
            )

        # Ensure connection is closed
        try:
            ws_state = websocket.client_state
            if (
                ws_state == websocket.client_state.CONNECTED
                or ws_state == websocket.client_state.CONNECTING
            ):
                await websocket.close()
                log.info(
                    f"WebSocket conn explicitly closed for "
                    f"{websocket.client} during cleanup."
                )
        except RuntimeError as e:
            log.warning(
                f"RuntimeError closing websocket during cleanup "
                f"(likely already closed): {e}"
            )
        except Exception as e:
            log.error(
                f"Unexpected error closing websocket during cleanup: {e}",
                exc_info=True,
            )


# --- Root path to serve the HTML file ---
@app.get("/")
async def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    log.error("index.html not found at expected path.")
    return {"error": "Frontend file not found."}, 404


# --- Optional Debug Endpoint ---
@app.get("/sessions")
async def get_sessions():
    """Returns the number of currently active WebSocket sessions."""
    return {"active_sessions": len(active_sessions)}