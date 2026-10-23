"""Offline EvoLink contract + policy tests: no browser, key, or network needed."""

from copy import deepcopy
from unittest.mock import Mock

import httpx
import pytest

from jev_ultrafast import luna_decisions, model


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("DECISION_PROVIDER", "evolink")
    monkeypatch.setenv("EVOLINK_API_KEY", "offline-placeholder")
    monkeypatch.delenv("EVOLINK_BASE_URL", raising=False)
    monkeypatch.delenv("EVOLINK_MODEL", raising=False)
    # Any accidental real HTTP path fails locally before sending data.
    monkeypatch.setattr(model.CLIENT, "post", Mock(side_effect=AssertionError("Network forbidden in tests")))


def page():
    return {"url": "https://example.test", "title": "Search", "text": "Find books", "actions": [
        {"id": "e1", "kind": "fill", "node": 1, "label": "Search", "role": "textbox", "value": ""},
        {"id": "e2", "kind": "click", "node": 2, "label": "Go", "role": "button"},
        {"id": "wait", "kind": "wait", "label": "Wait"},
    ]}


def reply(body, operation="CLICK"):
    return {"model": "gpt-6-luna", "usage": {"input_tokens": 101, "output_tokens": 0}, "answers": [
        {"name": q["name"], "type": "choice",
         "choice": operation if q["name"] == "operation" else q["choices"][0]["value"],
         "confidence": 0.9,
         "probabilities": [
             {"value": c["value"], "probability": float(c["value"] == (
                 operation if q["name"] == "operation" else q["choices"][0]["value"]))}
             for c in q["choices"]]}
        for q in body["questions"]]}


def test_real_wire_contract_click_and_all_heads_in_one_request(monkeypatch):
    def post(url, key, body):
        assert url == "https://direct.evolink.ai/v1/decisions"
        assert key == "offline-placeholder"
        assert set(body) == {"model", "input", "questions"}
        assert body["model"] == "gpt-6-luna-decisions"
        assert isinstance(body["input"], str)
        assert {q["name"] for q in body["questions"]} == {"operation", "click_target", "type_text_target"}
        assert all(set(q) == {"type", "name", "instructions", "choices"} for q in body["questions"])
        assert all(isinstance(c["value"], str) and isinstance(c["description"], str)
                   for q in body["questions"] for c in q["choices"])
        return reply(body)
    transport = Mock(side_effect=post)
    monkeypatch.setattr(model, "post_json", transport)
    state = page()
    state["actions"].extend([
        {"id": "e3", "kind": "click", "node": 3, "label": "Help", "role": "button"},
        {"id": "e4", "kind": "fill", "node": 4, "label": "Author", "role": "textbox", "value": ""},
    ])
    actual = model.choose(state, "Find books", [])
    assert actual["operation"] == "CLICK" and actual["choice"] == "e2"
    assert actual["usage"]["input_tokens"] == 101
    assert transport.call_count == 1


def test_singleton_targets_are_resolved_without_invalid_choice_questions(monkeypatch):
    def post(_url, _key, body):
        assert [q["name"] for q in body["questions"]] == ["operation"]
        assert all(len(q["choices"]) >= 2 for q in body["questions"])
        return reply(body)
    monkeypatch.setattr(model, "post_json", post)
    actual = model.choose(page(), "Find books", [])
    assert actual["operation"] == "CLICK" and actual["choice"] == "e2"
    assert actual["target_probabilities"] == {"2": 1.0}


def test_unverified_completion_cannot_be_selected(monkeypatch):
    def post(_url, _key, body):
        operation = next(q for q in body["questions"] if q["name"] == "operation")
        assert "DONE" not in {c["value"] for c in operation["choices"]}
        result = reply(body)
        result["answers"][0]["choice"] = "DONE"
        return result
    monkeypatch.setattr(model, "post_json", post)
    with pytest.raises(ValueError, match="Invalid EvoLink"):
        model.choose(page(), "Find books", [], allow_done=False)


@pytest.mark.parametrize("operation,action", [("TYPE_TEXT", "e1"), ("WAIT", "wait"),
                                              ("DONE", "DONE"), ("BLOCKED", "BLOCKED")])
def test_operation_dispatch_preserves_original_policy(monkeypatch, operation, action):
    monkeypatch.setattr(model, "post_json", lambda _url, _key, body: reply(body, operation))
    assert model.choose(page(), "Find books", [])["choice"] == action


def test_native_dropdown_choice_stays_bound_to_observed_option(monkeypatch):
    state = page()
    state["actions"].append({"id": "e3", "kind": "select", "node": 3, "label": "Category → Books",
                             "value": "books", "current_value": "all"})
    monkeypatch.setattr(model, "post_json", lambda _url, _key, body: reply(body, "SELECT"))
    actual = model.choose(state, "Select books", [])
    assert actual["choice"] == "e3" and actual["target"] == "3:1"


@pytest.mark.parametrize("mutation", ["refusal", "unknown", "duplicate", "missing", "nan", "sum", "non_max"])
def test_bad_response_fails_before_execution(monkeypatch, mutation):
    def post(_url, _key, body):
        result = deepcopy(reply(body))
        a = result["answers"][0]
        if mutation == "refusal":
            a["type"] = "refusal"
        elif mutation == "unknown":
            a["choice"] = "invented"
        elif mutation == "duplicate":
            result["answers"].append(a)
        elif mutation == "missing":
            result["answers"].pop()
        elif mutation == "nan":
            a["confidence"] = float("nan")
        elif mutation == "sum":
            a["probabilities"][0]["probability"] = 0.5
        else:
            a["choice"] = "DONE"
        return result
    monkeypatch.setattr(model, "post_json", post)
    with pytest.raises(ValueError, match="Invalid EvoLink"):
        model.choose(page(), "Find books", [])


def test_missing_key_and_untrusted_endpoint_never_send(monkeypatch):
    post = Mock()
    monkeypatch.setattr(model, "post_json", post)
    monkeypatch.delenv("EVOLINK_API_KEY")
    with pytest.raises(ValueError, match="EVOLINK_API_KEY"):
        model.choose(page(), "Find books", [])
    monkeypatch.setenv("EVOLINK_API_KEY", "offline-placeholder")
    monkeypatch.setenv("EVOLINK_BASE_URL", "https://example.test")
    with pytest.raises(ValueError, match="documented"):
        model.choose(page(), "Find books", [])
    post.assert_not_called()


def test_fallback_is_explicit_and_model_alias_is_documented(monkeypatch):
    monkeypatch.setenv("EVOLINK_BASE_URL", "https://api.evolink.ai/")
    monkeypatch.setenv("EVOLINK_MODEL", "gpt-6-luna")
    assert luna_decisions.configuration() == (
        "https://api.evolink.ai/v1/decisions", "offline-placeholder", "gpt-6-luna"
    )
    monkeypatch.setenv("EVOLINK_MODEL", "luna-decision")
    with pytest.raises(ValueError):
        luna_decisions.configuration()


def test_http_error_never_echoes_key_or_provider_body(monkeypatch):
    transport = httpx.MockTransport(lambda _request: httpx.Response(401, text="private upstream detail"))
    with httpx.Client(transport=transport) as client:
        monkeypatch.setattr(model, "CLIENT", client)
        with pytest.raises(RuntimeError, match="^Model provider returned HTTP 401; no action executed.$"):
            model.choose(page(), "Find books", [])


def test_text_helper_is_separate_from_decisions(monkeypatch):
    monkeypatch.delenv("TEXT_MODEL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TEXT_MODEL_API_KEY"):
        model.field_text({"goal": "Enter a title"})
