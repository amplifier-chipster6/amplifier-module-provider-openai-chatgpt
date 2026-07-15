"""Tests for the shipped OpenAI ChatGPT routing matrix."""

from pathlib import Path
from typing import Any

import yaml

ROUTING_PATH = Path(__file__).resolve().parents[1] / "routing" / "openai-chatgpt.yaml"

EXPECTED_ROLES = {
    "general",
    "fast",
    "coding",
    "ui-coding",
    "security-audit",
    "reasoning",
    "critique",
    "creative",
    "writing",
    "research",
    "vision",
    "image-gen",
    "critical-ops",
}

EXPECTED_MODELS = {
    "general": ["gpt-5.6-sol", "gpt-5.5", "gpt-5.4"],
    "fast": ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.5"],
    "coding": ["gpt-?.?-codex*", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.5"],
    "ui-coding": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.5"],
    "security-audit": ["gpt-5.6-sol", "gpt-5.5"],
    "reasoning": ["gpt-5.6-sol", "gpt-5.5"],
    "critique": ["gpt-5.6-sol", "gpt-5.5"],
    "creative": ["gpt-5.6-sol", "gpt-5.5"],
    "writing": ["gpt-5.6-sol", "gpt-5.5"],
    "research": ["gpt-5.6-sol", "gpt-5.5"],
    "vision": ["gpt-5.6-sol", "gpt-5.5"],
    "image-gen": ["gpt-5.6-sol", "gpt-5.5"],
    "critical-ops": ["gpt-5.6-sol", "gpt-5.5"],
}

HIGH_EFFORT_ROLES = {"security-audit", "reasoning", "research", "critical-ops"}


def _load_routing() -> dict[str, Any]:
    return yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8"))


def _models_for_role(routing: dict[str, Any], role: str) -> list[str]:
    return [candidate["model"] for candidate in routing["roles"][role]["candidates"]]


def _candidates_for_role(routing: dict[str, Any], role: str) -> list[dict[str, Any]]:
    return routing["roles"][role]["candidates"]


def _first_candidate_for_role(routing: dict[str, Any], role: str) -> dict[str, Any]:
    return _candidates_for_role(routing, role)[0]


def test_all_expected_roles_are_defined() -> None:
    routing = _load_routing()

    assert set(routing["roles"]) == EXPECTED_ROLES


def test_role_candidate_models_match_gpt_5_6_rollout_matrix() -> None:
    routing = _load_routing()

    for role, models in EXPECTED_MODELS.items():
        assert _models_for_role(routing, role) == models


def test_default_roles_prefer_gpt_5_6_sol() -> None:
    routing = _load_routing()

    for role in {"general", "ui-coding", "creative", "writing", "vision", "image-gen"}:
        assert _models_for_role(routing, role)[0] == "gpt-5.6-sol"


def test_reasoning_roles_prefer_gpt_5_6_sol_high_effort() -> None:
    routing = _load_routing()

    for role in HIGH_EFFORT_ROLES:
        candidate = _first_candidate_for_role(routing, role)
        assert candidate["model"] == "gpt-5.6-sol"
        assert candidate["config"]["reasoning_effort"] == "high"


def test_reasoning_roles_keep_high_effort_on_legacy_fallback() -> None:
    routing = _load_routing()

    for role in HIGH_EFFORT_ROLES:
        fallback = _candidates_for_role(routing, role)[1]
        assert fallback["model"] == "gpt-5.5"
        assert fallback["config"]["reasoning_effort"] == "high"


def test_critique_prefers_gpt_5_6_sol_xhigh_effort() -> None:
    routing = _load_routing()

    candidate = _first_candidate_for_role(routing, "critique")

    assert candidate["model"] == "gpt-5.6-sol"
    assert candidate["config"]["reasoning_effort"] == "xhigh"


def test_critique_keeps_xhigh_effort_on_legacy_fallback() -> None:
    routing = _load_routing()

    fallback = _candidates_for_role(routing, "critique")[1]

    assert fallback["model"] == "gpt-5.5"
    assert fallback["config"]["reasoning_effort"] == "xhigh"


def test_fast_prefers_gpt_5_6_luna() -> None:
    routing = _load_routing()

    assert _models_for_role(routing, "fast")[0] == "gpt-5.6-luna"


def test_coding_prefers_codex_then_gpt_5_6_terra() -> None:
    routing = _load_routing()

    assert _models_for_role(routing, "coding")[:2] == [
        "gpt-?.?-codex*",
        "gpt-5.6-terra",
    ]


def test_every_role_includes_gpt_5_5_fallback() -> None:
    routing = _load_routing()

    for role in EXPECTED_ROLES:
        assert "gpt-5.5" in _models_for_role(routing, role)
