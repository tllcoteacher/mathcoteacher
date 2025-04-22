# webserver/main.py
import json  # Used in exception handling potentially
import logging
import os  # To build file paths

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
    # IncomingMessage # Not strictly needed with the current parsing logic
)

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)  # Use a named logger
app = FastAPI()

# --- Static Files Setup ---
# Serve files from the 'static' directory located one level above this file's directory
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- WebSocket Logic ---

# Dictionary to hold active assessment sessions (key: websocket, value: session object)
active_sessions: dict[WebSocket, AssessmentSession] = {}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    log.info(f"WebSocket connection accepted from {websocket.client}.")
    session: AssessmentSession | None = (
        None  # Initialize session variable for this connection
    )

    try:
        while True:
            # Wait for a message (expecting JSON)
            try:
                raw_data = await websocket.receive_json()
                log.info(f"Received raw data: {raw_data}")

                # --- Pydantic Validation ---
                try:
                    # 1. First, parse into the BaseMessage to safely get the type and common fields
                    base_msg = BaseMessage.parse_obj(raw_data)
                    log.info(f"Parsed base message type: {base_msg.type}")

                    # 2. Based on the type, parse into the specific Pydantic model for full validation
                    # We store the fully validated Pydantic object in 'validated_data'
                    validated_data: BaseMessage  # Type hint for clarity

                    if base_msg.type == "draw_stroke":
                        validated_data = DrawStrokeMessage.parse_obj(raw_data)
                        log.info("Validated as DrawStrokeMessage.")
                    elif base_msg.type == "action_complete":
                        validated_data = ActionCompleteMessage.parse_obj(raw_data)
                        log.info("Validated as ActionCompleteMessage.")
                    elif base_msg.type == "submit_text_response":
                        validated_data = SubmitTextResponseMessage.parse_obj(raw_data)
                        log.info("Validated as SubmitTextResponseMessage.")
                    else:
                        # This case should technically not be reachable if BaseMessage validation passed
                        # due to the Literal type hint, but better safe than sorry.
                        log.warning(
                            f"Unknown message type '{base_msg.type}' received after base parsing."
                        )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"Unknown message type: {base_msg.type}",
                            }
                        )
                        continue  # Skip processing this message

                except ValidationError as e:
                    # Pydantic validation failed! Log the detailed error.
                    log.error(
                        f"Validation failed for data: {raw_data}\nError: {e.json(indent=2)}"
                    )  # Log detailed validation error
                    # Send a user-friendly error message back to the client
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Invalid message format received.",
                            # You could add more details here if needed for debugging on the client
                            # "details": json.loads(e.json()), # Send Pydantic error details
                        }
                    )
                    continue  # Skip processing this invalid message, wait for the next one

                # --- Session Management (Create session on first valid message) ---
                if session is None:
                    try:
                        # Use the validated task_id from the message
                        # For now, we still hardcode '6x8' as per original logic, but could use validated_data.task_id
                        task_id_to_use = "6x8"  # Or potentially: validated_data.task_id
                        session = AssessmentSession(task_id=task_id_to_use)
                        active_sessions[websocket] = session
                        log.info(
                            f"Created AssessmentSession for task '{task_id_to_use}' for {websocket.client}. Total sessions: {len(active_sessions)}"
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
                        break  # Close connection if session fails to initialize (e.g., bad rules file)
                    except Exception as e:
                        log.error(
                            f"Unexpected error creating session for task '{task_id_to_use}': {e}",
                            exc_info=True,
                        )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Internal server error during session creation.",
                            }
                        )
                        break  # Close connection on unexpected error

                # --- Process Event through Engine ---
                # We now pass the fully validated Pydantic object to the engine
                # **** IMPORTANT REMINDER ****
                # Your AssessmentSession.process_event method needs to be updated
                # to correctly handle these Pydantic model objects
                # (DrawStrokeMessage, ActionCompleteMessage, SubmitTextResponseMessage)
                # instead of just a raw dictionary.
                # **************************
                if (
                    session
                ):  # Should always be true after the block above, but check anyway
                    try:
                        action_to_send = session.process_event(
                            validated_data
                        )  # Pass validated Pydantic model

                        if action_to_send:
                            await websocket.send_json(action_to_send)
                            log.info(f"Action sent: {action_to_send}")

                        if session.assessment_complete:
                            log.info(
                                f"Assessment complete flag set for session with {websocket.client}."
                            )
                            # Decide whether to break or keep connection open
                            # break # Option: Close connection immediately on completion

                    except Exception as e:
                        log.error(
                            f"Error processing event in engine: {e}", exc_info=True
                        )
                        await websocket.send_json(
                            {"type": "error", "message": "Error processing event."}
                        )
                        # Option: break here if engine errors should terminate connection?

            except WebSocketDisconnect:
                # Client closed the connection gracefully
                log.info(f"WebSocket disconnected by client: {websocket.client}")
                break  # Exit the while loop
            except json.JSONDecodeError:
                # Handle cases where the received data isn't valid JSON at all
                log.warning(
                    f"Received non-JSON message from {websocket.client}, ignoring."
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid data format. Please send JSON.",
                    }
                )
                # Continue waiting for the next message
            except Exception as e:
                # Catch other potential receive errors or unexpected issues in the loop
                log.error(
                    f"Error during WebSocket receive/process loop for {websocket.client}: {e}",
                    exc_info=True,
                )
                # Attempt to send a generic error before breaking
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "An internal server error occurred.",
                        }
                    )
                except Exception:
                    log.error("Failed to send error message before closing connection.")
                break  # Break the loop on significant errors

    except Exception as e:
        # Catch unexpected errors outside the main message loop but within endpoint scope
        log.error(
            f"Unexpected WebSocket error for {websocket.client}: {e}", exc_info=True
        )

    finally:
        # --- Cleanup ---
        log.info(f"Cleaning up connection for {websocket.client}")
        if websocket in active_sessions:
            # Optional: Call a cleanup method on the session if it exists
            # E.g., await active_sessions[websocket].handle_disconnect()
            del active_sessions[websocket]
            log.info(f"Removed session. Total sessions: {len(active_sessions)}")
        else:
            log.warning(
                "WebSocket not found in active sessions during cleanup (might have failed before session creation)."
            )

        # Ensure connection is closed if not already closed by disconnect exception
        try:
            # Check state before attempting to close again
            if (
                websocket.client_state == websocket.client_state.CONNECTED
                or websocket.client_state == websocket.client_state.CONNECTING
            ):
                await websocket.close()
                log.info(
                    f"WebSocket connection explicitly closed for {websocket.client} during cleanup."
                )
        except RuntimeError as e:
            # Can happen if the connection is already closing or closed abruptly
            log.warning(
                f"RuntimeError closing websocket during cleanup (likely already closed): {e}"
            )
        except Exception as e:
            log.error(
                f"Unexpected error closing websocket during cleanup: {e}", exc_info=True
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
