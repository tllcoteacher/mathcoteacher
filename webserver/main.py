from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import logging
import json # For parsing incoming JSON manually if needed, though receive_json is better

# Import our assessment engine class
from assessment_engine.engine import AssessmentSession

logging.basicConfig(level=logging.INFO)
app = FastAPI()

# --- Static Files Setup (same as before) ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- WebSocket Logic ---

# Dictionary to hold active assessment sessions (key: websocket, value: session object)
# This allows handling multiple connections, though unlikely for the initial prototype
active_sessions: dict[WebSocket, AssessmentSession] = {}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket connection accepted.")
    session = None # Initialize session variable for this connection

    try:
        while True:
            # Wait for a message (expecting JSON)
            try:
                event_data = await websocket.receive_json() # Use receive_json
                logging.info(f"JSON received: {event_data}")
            except json.JSONDecodeError:
                logging.error("Received non-JSON message, ignoring.")
                continue # Skip non-JSON messages
            except Exception as e:
                # Catch other potential receive errors
                logging.error(f"Error receiving data: {e}")
                break # Break the loop on receive error

            # --- Session Management ---
            # For the prototype, we'll assume the task is always '6x8'
            # A real app might determine task_id from URL or first message
            if session is None:
                try:
                    # Create a session for this websocket connection for task '6x8'
                    session = AssessmentSession(task_id="6x8")
                    active_sessions[websocket] = session
                    logging.info(f"Created AssessmentSession for task '6x8'.")
                except ValueError as e:
                    logging.error(f"Failed to create session: {e}")
                    # Send error back to client? Or just close.
                    await websocket.send_json({"type": "error", "message": "Failed to load task rules."})
                    break # Close connection if rules fail

            # --- Process Event through Engine ---
            if session:
                try:
                    action_to_send = session.process_event(event_data)

                    # If the engine determined an action, send it back
                    if action_to_send:
                        await websocket.send_json(action_to_send)
                        logging.info(f"Action sent: {action_to_send}")

                    # If assessment completed, maybe close connection or wait?
                    if session.assessment_complete:
                        logging.info("Assessment complete flag set for session.")
                        # Optionally break loop here, or wait for client to close
                        # For now, we'll let it stay open until client disconnects or error

                except Exception as e:
                    logging.error(f"Error processing event in engine: {e}", exc_info=True)
                    # Send error back to client?
                    await websocket.send_json({"type": "error", "message": "Error processing event."})

    except WebSocketDisconnect:
        logging.info("WebSocket disconnected.")
    except Exception as e:
        # Catch unexpected errors in the main loop
        logging.error(f"Unexpected WebSocket error: {e}", exc_info=True)
    finally:
        # --- Cleanup ---
        if websocket in active_sessions:
            del active_sessions[websocket]
            logging.info("Cleaned up session.")
        # Ensure connection is closed if not already
        try:
             # Check state before closing - avoid closing an already closed socket
             if websocket.client_state == websocket.client_state.CONNECTED:
                 await websocket.close()
                 logging.info("WebSocket connection closed during cleanup.")
        except Exception as e:
            logging.error(f"Error closing websocket during cleanup: {e}", exc_info=True)


# --- Root path (same as before) ---
@app.get("/")
async def read_root():
    return {"message": "Server is running. Go to /static/index.html"}