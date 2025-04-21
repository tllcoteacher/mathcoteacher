import yaml
import os
from pathlib import Path

# Define the base path for the rules directory
# Assumes rules/ is at the same level as the assessment_engine/ folder
RULES_DIR = Path(__file__).parent.parent / "rules"

def load_rule_file(task_id: str) -> dict | None:
    """Loads the YAML rule file for a specific task ID."""
    rule_file_path = RULES_DIR / f"{task_id}.yaml"
    if not rule_file_path.is_file():
        print(f"Error: Rule file not found at {rule_file_path}")
        return None
    try:
        with open(rule_file_path, 'r') as f:
            rules = yaml.safe_load(f)
        print(f"Successfully loaded rules for task: {task_id}")
        return rules
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {rule_file_path}: {e}")
        return None
    except Exception as e:
        print(f"Error loading rule file {rule_file_path}: {e}")
        return None

if __name__ == '__main__':
    # Example usage: Try loading the 6x8 rules when running this file directly
    rules_6x8 = load_rule_file("6x8")
    if rules_6x8:
        print("\nLoaded 6x8 Rules:")
        import json # Using json for pretty printing the dict
        print(json.dumps(rules_6x8, indent=2))