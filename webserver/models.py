# webserver/models.py
from typing import List, Literal, Union

from pydantic import BaseModel

# Define the possible incoming message types as string literals
# This helps ensure the 'type' field has one of the expected values.
IncomingMessageType = Literal[
    "draw_stroke",
    "action_complete",
    "submit_text_response",
]

# --- Specific Incoming Message Models ---
# Define the structure for each type of message the browser might send.


class DrawStrokeMessage(BaseModel):
    """Model for the 'draw_stroke' message."""

    type: Literal["draw_stroke"]  # Must be exactly "draw_stroke"
    task_id: str  # Must be a string
    # Assuming stroke_data is a list of numbers based on console logs.
    # Adjust List[int] if it's something else (e.g., List[List[int]] for points)
    stroke_data: List[int]


class ActionCompleteMessage(BaseModel):
    """Model for the 'action_complete' message."""

    type: Literal["action_complete"]  # Must be exactly "action_complete"
    task_id: str  # Must be a string


class SubmitTextResponseMessage(BaseModel):
    """Model for the 'submit_text_response' message."""

    type: Literal["submit_text_response"]  # Must be exactly "submit_text_response"
    task_id: str  # Must be a string
    text: str  # Must be a string


# --- Union Model for Type Dispatching ---
# This helps FastAPI figure out which specific model to use based on the 'type' field.
# It says an incoming message could be *one of* these specific types.
IncomingMessage = Union[
    DrawStrokeMessage,
    ActionCompleteMessage,
    SubmitTextResponseMessage,
]


# --- Generic Model for initial parsing (Optional but often useful) ---
# Sometimes it's easier to parse the 'type' field first, then parse
# into the specific model. This captures the common fields.
class BaseMessage(BaseModel):
    """A base model to initially parse messages and check their type."""

    type: IncomingMessageType  # The type must be one of the allowed literals
    task_id: str
