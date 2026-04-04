"""
Verification question flow configuration.

Each question is a dict with:
    id          – unique key, also used to store the answer in verification_status
    text        – message the agent sends to the worker
    options     – list of allowed reply strings
    ui_type     – "buttons" (≤3 options, WhatsApp reply buttons)
                  or "list" (>3 options, WhatsApp list / dropdown)
    condition   – optional callable(verification_status) → bool.
                  If provided, the question is only asked when condition returns True.
                  If None, the question is always asked.

To add / remove / reorder questions, simply edit the QUESTIONS list below.
To add conditional logic, set the ``condition`` key to a function that
receives the current verification_status dict and returns True/False.

Examples of future conditions:
    "condition": lambda vs: vs.get("available_in_14_days") == "Yes"
    "condition": lambda vs: vs.get("skill_category") == "driving"
"""

QUESTIONS: list[dict] = [
    {
        "id": "available_in_14_days",
        "text": "Are you available to start work in the next 14 days?",
        "options": ["Yes", "No"],
        "ui_type": "buttons",
        "condition": None,
    },
    {
        "id": "travel_distance",
        "text": "How far can you travel for work?",
        "options": ["Less than 10 km", "10-25 km", "More than 25 km"],
        "ui_type": "buttons",
        "condition": None,
    },
    {
        "id": "shift_preference",
        "text": "Are you comfortable working day shifts, night shifts, or both?",
        "options": ["Day", "Night", "Both"],
        "ui_type": "buttons",
        "condition": None,
    },
    {
        "id": "health_conditions",
        "text": "Do you have any health conditions that prevent physical work?",
        "options": ["Yes", "No"],
        "ui_type": "buttons",
        "condition": None,
    },
]


def get_next_question(verification_status: dict) -> dict | None:
    """
    Walk through QUESTIONS in order and return the first one whose ``id``
    is NOT yet answered (i.e. not a key in *verification_status*) and whose
    ``condition`` (if any) passes.

    Returns None when all applicable questions have been answered.
    """
    for q in QUESTIONS:
        # Already answered → skip
        if q["id"] in verification_status:
            continue

        # Evaluate condition (if present)
        cond = q.get("condition")
        if cond is not None and not cond(verification_status):
            continue

        return q

    return None


def is_valid_answer(question: dict, answer: str) -> bool:
    """Case-insensitive check that *answer* is one of the allowed options."""
    allowed = [opt.lower() for opt in question["options"]]
    return answer.strip().lower() in allowed
