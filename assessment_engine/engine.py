# assessment_engine/engine.py
import logging
from typing import Any, Dict, Optional, Set, Union

# Import the Pydantic models defined in the webserver module
try:
    from webserver.models import (
        ActionCompleteMessage,
        DrawStrokeMessage,  # Removed BaseMessage import
        SubmitTextResponseMessage,
    )

    IncomingEvent = Union[
        DrawStrokeMessage, ActionCompleteMessage, SubmitTextResponseMessage
    ]
except ImportError:
    logging.error(
        "Could not import Pydantic models. Type checking limited."
    )
    IncomingEvent = Dict[str, Any]
    DrawStrokeMessage = Dict[str, Any]
    ActionCompleteMessage = Dict[str, Any]
    SubmitTextResponseMessage = Dict[str, Any]

# Assuming loader is in the same directory or configured correctly in path
# --- Import Evidence Enum and Extractor ---
from .evidence import Evidence, extract_from_text
from .loader import load_rule_file

log = logging.getLogger(__name__)


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
            log.error(
                f"Failed to load rules for task {task_id}: {e}", exc_info=True
            )
            raise ValueError(
                f"Could not initialize session: Failed to load/parse rules for {task_id}"
            )

        self.collected_evidence: Set[Evidence] = set()
        self.probes_asked: Set[str] = set()
        self.assessment_complete: bool = False
        self.final_level: Optional[str] = None
        self.current_step_state: Dict[str, Any] = {}

    def process_event(
        self, event: IncomingEvent
    ) -> Optional[Dict[str, Any]]:
        """
        Processes an incoming event object and decides the next action.

        Uses Evidence enum and extractor functions.
        Returns a dictionary representing the action to send back, or None.
        """
        if self.assessment_complete:
            log.warning(
                f"Task {self.task_id}: Processing event after assessment complete."
            )
            return None

        action_to_send: Optional[Dict[str, Any]] = None
        new_evidence_this_step: Set[Evidence] = set()

        # --- Event Type Handling ---
        if isinstance(event, DrawStrokeMessage):
            stroke_count = self.current_step_state.get("stroke_count", 0) + 1
            self.current_step_state["stroke_count"] = stroke_count
            log.debug(f"Task {self.task_id}: Stroke {stroke_count} received.")

        elif isinstance(event, ActionCompleteMessage):
            log.info(f"Task {self.task_id}: Action complete received.")
            stroke_count = self.current_step_state.get("stroke_count", 0)
            if stroke_count == 1:
                new_evidence_this_step.add(Evidence.DRAW_ONE_STROKE)
            elif stroke_count > 1:
                new_evidence_this_step.add(Evidence.DRAW_MULTIPLE_STROKES)
            self.current_step_state["stroke_count"] = 0

            # --- Probe Logic ---
            combined_evidence = self.collected_evidence.union(
                new_evidence_this_step
            )
            # Ask probe if drawing occurred (and probe not asked yet)
            should_ask_probe = (
                Evidence.DRAW_ONE_STROKE in combined_evidence
                or Evidence.DRAW_MULTIPLE_STROKES in combined_evidence
            )
            if should_ask_probe and "P1_HOW_SOLVE" not in self.probes_asked:
                probe_rule = next(
                    (
                        p
                        for p in self.rules.get("probes", [])
                        if p["id"] == "P1_HOW_SOLVE"
                    ),
                    None,
                )
                if probe_rule:
                    action_to_send = {
                        "type": "ask_probe",
                        "text": probe_rule["text"],
                        "speak": probe_rule.get("speak", False),
                    }
                    self.probes_asked.add("P1_HOW_SOLVE")
                    log.info(
                        f"Task {self.task_id}: Sending probe P1_HOW_SOLVE "
                        f"based on drawing evidence."
                    )
                else:
                    log.warning(
                        f"Task {self.task_id}: Probe P1_HOW_SOLVE defined in logic "
                        f"but not found in rules file."
                    )

        elif isinstance(event, SubmitTextResponseMessage):
            log.info(
                f"Task {self.task_id}: Text response received: '{event.text}'"
            )
            extracted_text_evidence = extract_from_text(event.text)
            new_evidence_this_step.update(extracted_text_evidence)

            # --- Stop Condition / Level Assignment Logic ---
            combined_evidence = self.collected_evidence.union(
                new_evidence_this_step
            )
            stop_rules = self.rules.get("stop_conditions", [])
            sc1 = next((sc for sc in stop_rules if sc["id"] == "SC1"), None)
            stop_condition_met = False
            if sc1:
                required_for_sc1 = {
                    Evidence(ev_str)
                    for ev_str in sc1.get("required_evidence", [])
                }
                if required_for_sc1.issubset(combined_evidence):
                    stop_condition_met = True
                    log.info(f"Task {self.task_id}: Stop condition SC1 met.")

            if stop_condition_met:
                level_rules = self.rules.get("level_assignment", [])
                level_assigned = "Unknown (Placeholder)"  # Default
                for rule in level_rules:
                    required = {
                        Evidence(ev_str)
                        for ev_str in rule.get("required_evidence", [])
                    }
                    if required.issubset(combined_evidence):
                        level_assigned = rule["level"]
                        break
                self.final_level = level_assigned
                self.assessment_complete = True
                log.info(
                    f"Assessment complete for task {self.task_id}. "
                    f"Level assigned: {self.final_level}"
                )
                action_to_send = {
                    "type": "assessment_complete",
                    "task_id": self.task_id,
                    "result_summary": f"Task complete. Level: {self.final_level}",
                }

        # Fallback for non-Pydantic or unhandled types
        elif isinstance(event, dict):
            event_type = event.get("type")
            log.warning(
                f"Task {self.task_id}: Processing event type '{event_type}' as Dictionary."
            )
            if event_type == "submit_text_response":
                extracted = extract_from_text(event.get("text", ""))
                new_evidence_this_step.update(extracted)
        else:
            log.error(
                f"Task {self.task_id}: Received invalid/unhandled event format: "
                f"{type(event)}"
            )
            action_to_send = {
                "type": "error",
                "message": "Invalid event format received by engine.",
            }

        # --- Update Master Evidence Log ---
        if new_evidence_this_step:
            self.collected_evidence.update(new_evidence_this_step)
            log.info(
                f"Task {self.task_id}: Added evidence {new_evidence_this_step}. "
                f"Log now: {self.collected_evidence}"
            )

        log.debug(
            f"Task {self.task_id}: process_event returning action: {action_to_send}"
        )
        return action_to_send


# Keep the example usage block
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        session = AssessmentSession(
            task_id="6x8"
        )  # Ensure rules/6x8.yaml exists
        log.info("\nSession Initialized.")

        log.info("\nSimulating draw events...")
        session.process_event(
            {"type": "draw_stroke", "task_id": "6x8", "stroke_data": [1]}
        )
        session.process_event(
            {"type": "draw_stroke", "task_id": "6x8", "stroke_data": [2]}
        )

        log.info("\nSimulating action_complete event...")
        action = session.process_event(
            {"type": "action_complete", "task_id": "6x8"}
        )
        log.info(f"Action to send: {action}")

        if action and action["type"] == "ask_probe":
            log.info("\nSimulating submit_text_response event...")
            action = session.process_event(
                {
                    "type": "submit_text_response",
                    "task_id": "6x8",
                    "text": "I count them all",
                }
            )
            log.info(f"Action to send: {action}")
        else:
            log.info("Skipping text response simulation as no probe was asked.")

    except ValueError as e:
        log.error(f"Standalone test failed: {e}")
    except FileNotFoundError:
        log.error("Standalone test failed: Could not find rules file.")
    except Exception as e:
        log.error(
            f"Standalone test failed with unexpected error: {e}", exc_info=True
        )