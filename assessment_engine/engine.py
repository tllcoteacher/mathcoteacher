# assessment_engine/engine.py
import logging
from typing import Any, Dict, List, Optional, Set, Union # Added Set, Union

# Assuming loader is in the same directory or configured correctly in path
from .loader import load_rule_file

# Import the Pydantic models defined in the webserver module
# This relative path assumes webserver is a sibling directory or accessible
try:
    from webserver.models import (
        DrawStrokeMessage,
        ActionCompleteMessage,
        SubmitTextResponseMessage,
        BaseMessage # Useful for type hinting base properties
    )
    # Define a type hint for the event parameter that covers all valid incoming types
    IncomingEvent = Union[DrawStrokeMessage, ActionCompleteMessage, SubmitTextResponseMessage]
except ImportError:
    # Fallback if running engine.py standalone or models are not found
    logging.error("Could not import Pydantic models from webserver.models. Type checking in process_event might be limited.")
    # Define basic types for fallback - note this bypasses Pydantic benefits in standalone runs
    IncomingEvent = Dict[str, Any] # Fallback to dictionary
    DrawStrokeMessage = Dict[str, Any]
    ActionCompleteMessage = Dict[str, Any]
    SubmitTextResponseMessage = Dict[str, Any]


log = logging.getLogger(__name__) # Use a named logger

class AssessmentSession:
    """Manages the state for a single student assessment session."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        log.info(f"Initializing AssessmentSession for task: {task_id}")
        try:
            self.rules = load_rule_file(task_id)
            if not self.rules:
                 raise ValueError("Loaded rules are empty or invalid.")
            log.info(f"Successfully loaded rules for task: {task_id}")
        except Exception as e:
             log.error(f"Failed to load rules for task {task_id}: {e}", exc_info=True)
             # Raise a specific error that the calling code (main.py) can catch
             raise ValueError(f"Could not initialize session: Failed to load or parse rules for {task_id}")

        self.collected_evidence: Set[str] = set() # Use Set type hint
        self.probes_asked: Set[str] = set()       # Use Set type hint
        self.assessment_complete: bool = False
        self.final_level: Optional[str] = None    # Use Optional type hint

        # Placeholder for state tracked during a multi-part action (like drawing)
        self.current_step_state: Dict[str, Any] = {}


    def process_event(self, event: IncomingEvent) -> Optional[Dict[str, Any]]:
        """
        Processes an incoming event object (validated by Pydantic) and decides the next action.
        Returns a dictionary representing the action to send back (e.g., a probe), or None.
        --- UPDATED FOR Pydantic Objects ---
        """
        if self.assessment_complete:
            log.warning(f"Task {self.task_id}: Processing event after assessment complete.")
            return None

        # Check if the input is a Pydantic model (primary path) or dict (fallback)
        if hasattr(event, 'type'): # Check if it looks like our Pydantic model
            event_type = event.type
            task_id = event.task_id # Access task_id directly
            log.debug(f"Task {self.task_id}: Processing event type '{event_type}' (Pydantic Model)")
        elif isinstance(event, dict) and "type" in event: # Fallback for dict
            event_type = event.get("type")
            task_id = event.get("task_id")
            log.warning(f"Task {self.task_id}: Processing event type '{event_type}' as Dictionary (Pydantic import might have failed)")
        else:
            log.error(f"Task {self.task_id}: Received invalid event data format: {event}")
            return {"type": "error", "message": "Invalid event format received by engine."}


        action_to_send: Optional[Dict[str, Any]] = None # Use Optional type hint

        # --- Simplified Rule Application using isinstance and attribute access ---

        # 1. If student drew anything, update internal state (like stroke count)
        #    React only when the action is complete.
        if isinstance(event, DrawStrokeMessage):
            # Add logic here later to analyze event.stroke_data if needed
            stroke_count = self.current_step_state.get("stroke_count", 0) + 1
            self.current_step_state["stroke_count"] = stroke_count
            log.debug(f"Task {self.task_id}: Stroke {stroke_count} received.")
            # No immediate action sent back for just a stroke

        # 2. When student clicks "Done" (action_complete), finalize evidence for the step
        #    and check if we need to probe.
        elif isinstance(event, ActionCompleteMessage):
            log.info(f"Task {self.task_id}: Action complete received.")
            # Finalize evidence based on the completed action (e.g., drawing)
            stroke_count = self.current_step_state.get("stroke_count", 0)
            if stroke_count > 0:
                 self.collected_evidence.add("DRAW_ANY") # Add evidence now
                 log.info(f"Task {self.task_id}: Added evidence 'DRAW_ANY' based on {stroke_count} strokes.")

            # Reset step state after processing
            self.current_step_state["stroke_count"] = 0

            # Check if probe P1 needs to be asked (based on your original logic)
            if "DRAW_ANY" in self.collected_evidence and "P1_HOW_SOLVE" not in self.probes_asked:
                probe_to_ask = next((p for p in self.rules.get("probes", []) if p["id"] == "P1_HOW_SOLVE"), None)
                if probe_to_ask:
                    action_to_send = {
                        "type": "ask_probe",
                        "text": probe_to_ask["text"],
                        "speak": probe_to_ask.get("speak", False) # Keep .get() for dict access within rules data
                    }
                    self.probes_asked.add("P1_HOW_SOLVE")
                    log.info(f"Task {self.task_id}: Sending probe P1_HOW_SOLVE.")
                else:
                    log.warning(f"Task {self.task_id}: Probe P1_HOW_SOLVE defined in logic but not found in rules file.")


        # 3. If student submits text, add evidence and check stop condition
        elif isinstance(event, SubmitTextResponseMessage):
            log.info(f"Task {self.task_id}: Text response received: '{event.text}'") # Access event.text
            self.collected_evidence.add("ANSWER_TYPED")
            log.info(f"Task {self.task_id}: Added evidence 'ANSWER_TYPED'.")

            # Check if stop condition met (ANSWER_TYPED is enough for SC1 in simplified rules)
            # Note: Accessing self.rules safely, assuming it was loaded in __init__
            stop_rules = self.rules.get("stop_conditions", [])
            sc1 = next((sc for sc in stop_rules if sc["id"] == "SC1"), None)
            stop_condition_met = False
            if sc1 and all(ev in self.collected_evidence for ev in sc1.get("required_evidence", [])):
                 stop_condition_met = True
                 log.info(f"Task {self.task_id}: Stop condition SC1 met.")

            if stop_condition_met:
                # Assign placeholder level based on simplified rule (matching original logic)
                level_rules = self.rules.get("level_assignment", [])
                sd1_1_rule = next((lr for lr in level_rules if lr["level"] == "SD1_1 (Placeholder)"), None) # Assuming placeholder name is unique ID for now
                if sd1_1_rule and all(ev in self.collected_evidence for ev in sd1_1_rule.get("required_evidence", [])):
                     self.final_level = sd1_1_rule["level"]
                else:
                    self.final_level = "Unknown (Placeholder)" # Default if no rules match

                self.assessment_complete = True
                log.info(f"Assessment complete for task {self.task_id}. Level assigned: {self.final_level}")
                action_to_send = {
                    "type": "assessment_complete",
                    "task_id": self.task_id, # Use self.task_id stored in session
                    "result_summary": f"Task complete. Level: {self.final_level}"
                }
        else:
             log.warning(f"Task {self.task_id}: Unhandled event type '{event_type}' in process_event logic.")


        log.debug(f"Task {self.task_id}: process_event returning action: {action_to_send}")
        return action_to_send


# Keep the example usage block if you run this file directly for testing
# Note: It will likely use the Dict fallback path now unless webserver models are importable
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO) # Setup basic logging for standalone run
    try:
        session = AssessmentSession(task_id="6x8") # Ensure rules/6x8.yaml exists relative to where you run this
        log.info("\nSession Initialized.")

        # Simulate drawing event
        log.info("\nSimulating draw event...")
        session.process_event({"type": "draw_stroke", "task_id": "6x8", "stroke_data": [1,2,3]}) # Use dict for standalone test

        # Simulate clicking "Done"
        log.info("\nSimulating action_complete event...")
        action = session.process_event({"type": "action_complete", "task_id": "6x8"}) # Use dict
        log.info(f"Action to send: {action}")

        # Simulate typing an answer
        log.info("\nSimulating submit_text_response event...")
        action = session.process_event({"type": "submit_text_response", "task_id": "6x8", "text": "I counted them"}) # Use dict
        log.info(f"Action to send: {action}")

    except ValueError as e:
         log.error(f"Standalone test failed: {e}")
    except FileNotFoundError:
         log.error("Standalone test failed: Could not find the rules file (e.g., rules/6x8.yaml). Make sure it exists relative to execution path.")