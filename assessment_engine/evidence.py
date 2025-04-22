# assessment_engine/evidence.py
import logging
from enum import Enum
from typing import Set  # Moved import to top

log = logging.getLogger(__name__)


class Evidence(str, Enum):
    """
    Enumeration of specific evidence codes derived from student actions.

    Using str mixin so the enum members can be easily compared and serialized
    (e.g., to JSON or YAML).
    """

    # === General Actions ===
    DRAW_ANY = "DRAW_ANY"  # Any drawing action occurred (may be replaced by specifics)
    ANSWER_TYPED = "ANSWER_TYPED"  # Any text answer was typed

    # === Drawing Specific (Example Refinements) ===
    DRAW_ONE_STROKE = "DRAW_ONE_STROKE"  # Exactly one stroke was made in an action phase
    DRAW_MULTIPLE_STROKES = (
        "DRAW_MULTIPLE_STROKES"  # More than one stroke was made
    )

    # === Text Specific (Example Refinements) ===
    EVIDENCE_SAID_COUNT = (
        "EVIDENCE_SAID_COUNT"  # Student response included "count" (case-insensitive)
    )

    # === Add more specific evidence codes as needed ===
    # e.g., DREW_GROUPS, DREW_ARRAY, SAID_MULTIPLY, USED_NUMBER_LINE, etc.

    # You can add helper methods here if needed later, e.g.,
    # @classmethod
    # def is_drawing_evidence(cls, code: str) -> bool:
    #     return code.startswith("DRAW_")


# --- Evidence Extractor Functions ---


def extract_from_text(text: str) -> Set[Evidence]:
    """
    Analyzes the input text and returns a set of derived Evidence codes.

    Args:
        text: The text string submitted by the student.

    Returns:
        A set containing Evidence enum members found based on the text.
    """
    if not text:  # Handle empty input
        return set()

    extracted: Set[Evidence] = set()
    text_lower = text.lower()  # Convert to lowercase for case-insensitive matching

    # Basic evidence: any text was typed
    extracted.add(Evidence.ANSWER_TYPED)

    # Specific evidence: check for keywords
    if "count" in text_lower:
        extracted.add(Evidence.EVIDENCE_SAID_COUNT)
        log.debug("Evidence found: EVIDENCE_SAID_COUNT")

    # --- Add more text analysis rules here ---
    # Example:
    # if "multiply" in text_lower or "times" in text_lower:
    #     extracted.add(Evidence.SAID_MULTIPLY) # Add SAID_MULTIPLY to Enum first!
    #     log.debug("Evidence found: SAID_MULTIPLY")
    #
    # Example: Check for number patterns, etc.
    # ---

    log.debug(f"Evidence extracted from text '{text}': {extracted}")
    return extracted


# --- Extractor for Drawing ---
# We will handle drawing evidence (like stroke count) within the
# AssessmentSession.process_event method when an 'action_complete' event
# arrives, because it depends on state accumulated across multiple 'draw_stroke'
# events (the stroke_count).