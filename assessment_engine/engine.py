from .loader import load_rule_file # Import the loader from the same package

class AssessmentSession:
    """Manages the state for a single student assessment session."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.rules = load_rule_file(task_id)
        self.collected_evidence = set() # Keep track of evidence codes found
        self.probes_asked = set() # Keep track of probe IDs asked
        self.assessment_complete = False
        self.final_level = None

        if not self.rules:
            raise ValueError(f"Could not initialize session: Failed to load rules for {task_id}")

    def process_event(self, event_data: dict) -> dict | None:
        """
        Processes an incoming event (like drawing, text) and decides the next action.
        Returns a dictionary representing the action to send back (e.g., a probe), or None.
        --- VERY SIMPLIFIED LOGIC FOR NOW ---
        """
        if self.assessment_complete:
            print("Warning: Processing event after assessment complete.")
            return None

        event_type = event_data.get("type")
        action_to_send = None

        # --- Trivial Rule Application ---
        # 1. If student drew anything, add DRAW_ANY evidence
        if event_type == "draw_stroke":
             self.collected_evidence.add("DRAW_ANY")
             # Don't react immediately to every stroke, wait for action_complete

        # 2. When student clicks "Done" after drawing, check if we need to probe
        elif event_type == "action_complete":
            if "DRAW_ANY" in self.collected_evidence and "P1_HOW_SOLVE" not in self.probes_asked:
                # Find the probe details from rules
                probe_to_ask = next((p for p in self.rules.get("probes", []) if p["id"] == "P1_HOW_SOLVE"), None)
                if probe_to_ask:
                    action_to_send = {
                        "type": "ask_probe",
                        "text": probe_to_ask["text"],
                        "speak": probe_to_ask.get("speak", False)
                    }
                    self.probes_asked.add("P1_HOW_SOLVE")

        # 3. If student submits text, add ANSWER_TYPED evidence and check stop condition
        elif event_type == "submit_text_response":
            self.collected_evidence.add("ANSWER_TYPED")
            # Check if stop condition met (ANSWER_TYPED is enough for SC1)
            stop_condition_met = "ANSWER_TYPED" in self.collected_evidence # Simplified check
            if stop_condition_met:
                # Assign placeholder level based on simplified rule
                if "DRAW_ANY" in self.collected_evidence and "ANSWER_TYPED" in self.collected_evidence:
                    self.final_level = "SD1_1 (Placeholder)" # Hardcoded for now based on rule file
                else:
                    self.final_level = "Unknown (Placeholder)"

                self.assessment_complete = True
                print(f"Assessment complete for task {self.task_id}. Level: {self.final_level}")
                action_to_send = {
                    "type": "assessment_complete",
                    "task_id": self.task_id,
                    "result_summary": f"Task complete. Level: {self.final_level}"
                }

        return action_to_send

# Example usage (optional, for testing if needed)
if __name__ == '__main__':
    session = AssessmentSession(task_id="6x8")
    print("\nSession Initialized. Rules loaded.")

    # Simulate drawing event (just type, data ignored for now)
    print("\nSimulating draw event...")
    session.process_event({"type": "draw_stroke", "task_id": "6x8", "stroke_data": {}})

    # Simulate clicking "Done"
    print("\nSimulating action_complete event...")
    action = session.process_event({"type": "action_complete", "task_id": "6x8"})
    print(f"Action to send: {action}")

    # Simulate typing an answer
    print("\nSimulating submit_text_response event...")
    action = session.process_event({"type": "submit_text_response", "task_id": "6x8", "text": "I did stuff"})
    print(f"Action to send: {action}")