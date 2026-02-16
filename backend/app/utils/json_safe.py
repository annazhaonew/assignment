"""
Safely parse JSON from LLM output with fallback extraction.
"""

import json
import re


def safe_parse_json(raw: str) -> dict | None:
    """Try json.loads first, then attempt to extract a JSON substring."""
    # Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block between ```json ... ``` or { ... }
    patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"(\{.*\})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    return None
