# tests/assessment_engine/test_evidence.py

import pytest # Import the pytest library itself (good practice)
from assessment_engine.evidence import Evidence, extract_evidence_from_event

# Define our first test function
def test_extract_draw_line_evidence():
    """
    Tests that a 'draw_line' event correctly extracts DREW_LINE evidence.
    """
    # 1. Arrange: Create a sample event simulating a draw_line action
    mock_event = {
        "action": "draw_line",
        "payload": {
            "tool": "pencil",
            "points": [0, 0, 10, 10], # Example data, content doesn't matter much for this specific test
            "strokeWidth": 2,
            "color": "black"
        }
    }

    # 2. Act: Call the function we are testing
    extracted_evidence = extract_evidence_from_event(mock_event)

    # 3. Assert: Check if the result is what we expect
    assert extracted_evidence == Evidence.DREW_LINE

# --- We can add more test functions below later ---