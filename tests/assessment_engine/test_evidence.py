# tests/assessment_engine/test_evidence.py

import pytest
from assessment_engine.evidence import Evidence, extract_from_text

# Test function for the extract_from_text utility
def test_extract_from_text_finds_count():
    """
    Tests that 'count' keyword correctly extracts EVIDENCE_SAID_COUNT
    and the general ANSWER_TYPED evidence.
    """
    # 1. Arrange: Define sample input text
    input_text = "I think I need to count them."
    expected_evidence = {Evidence.ANSWER_TYPED, Evidence.EVIDENCE_SAID_COUNT}

    # 2. Act: Call the function we are testing
    extracted_evidence = extract_from_text(input_text)

    # 3. Assert: Check if the result is what we expect
    # Using set comparison handles order differences
    assert extracted_evidence == expected_evidence

def test_extract_from_text_finds_only_typed():
    """
    Tests that text without specific keywords only extracts ANSWER_TYPED.
    """
    # 1. Arrange
    input_text = "Just moving things around."
    expected_evidence = {Evidence.ANSWER_TYPED}

    # 2. Act
    extracted_evidence = extract_from_text(input_text)

    # 3. Assert
    assert extracted_evidence == expected_evidence

def test_extract_from_text_empty_input():
    """
    Tests that empty text returns an empty set of evidence.
    """
    # 1. Arrange
    input_text = ""
    expected_evidence = set() # An empty set

    # 2. Act
    extracted_evidence = extract_from_text(input_text)

    # 3. Assert
    assert extracted_evidence == expected_evidence

# --- Add more test functions for extract_from_text as needed ---