"""EvoLink Decisions wire adapter. No SDK, credentials, retries, or browser execution."""

import json
import os

MODELS = {"gpt-6-luna-decisions", "gpt-6-luna"}
BASES = {"https://direct.evolink.ai", "https://api.evolink.ai"}


def configuration():
    key = os.environ.get("EVOLINK_API_KEY", "").strip()
    if not key:
        raise ValueError("Set EVOLINK_API_KEY in your local environment before live use; no request sent.")
    base = os.environ.get("EVOLINK_BASE_URL", "https://direct.evolink.ai").rstrip("/")
    model = os.environ.get("EVOLINK_MODEL", "gpt-6-luna-decisions")
    if base not in BASES or model not in MODELS:
        raise ValueError("Use a documented EvoLink Decisions endpoint and model ID; no request sent.")
    return base + "/v1/decisions", key, model


def request_body(state, questions, model):
    return {
        "model": model,
        "input": json.dumps(state, ensure_ascii=False),
        "questions": [
            {
                "type": "choice",
                "name": name,
                "instructions": json.dumps(question["instructions"], ensure_ascii=False),
                "choices": [
                    {"value": value, "description": json.dumps(description, ensure_ascii=False)}
                    for value, description in question["criteria"].items()
                ],
            }
            for name, question in questions.items()
            if len(question["criteria"]) > 1
        ],
    }


def normalize(result, questions, validate):
    """Reject refusals and malformed/unoffered choices before returning to the policy."""
    try:
        answers = result["answers"]
        offered = {name: question for name, question in questions.items() if len(question["criteria"]) > 1}
        if not isinstance(answers, list) or len(answers) != len(offered):
            raise ValueError()
        # A singleton target needs no prediction and is not a valid Decisions choice question.
        normalized = {
            name: validate({"choice": next(iter(q["criteria"])), "confidence": 1.0,
                            "probabilities": {next(iter(q["criteria"])): 1.0}}, q["criteria"])
            for name, q in questions.items() if len(q["criteria"]) == 1
        }
        for answer in answers:
            name = answer["name"]
            if answer["type"] != "choice" or name not in offered or name in normalized:
                raise ValueError()
            rows = answer["probabilities"]
            probabilities = {row["value"]: row["probability"] for row in rows}
            if len(rows) != len(probabilities):
                raise ValueError()
            normalized[name] = validate(
                {"choice": answer["choice"], "confidence": answer["confidence"], "probabilities": probabilities},
                questions[name]["criteria"],
            )
        if not isinstance(result["model"], str):
            raise ValueError()
        return {**result, "answers": normalized}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Invalid EvoLink decision response or refusal; no action executed.") from None
