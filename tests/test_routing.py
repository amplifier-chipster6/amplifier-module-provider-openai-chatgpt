"""Contract tests for the documented GPT-5.6 routing policy."""

from pathlib import Path

import yaml


MATRIX_PATH = Path(__file__).parents[1] / "routing" / "openai-chatgpt.yaml"


def _roles() -> dict:
    return yaml.safe_load(MATRIX_PATH.read_text())["roles"]


def _models(role: dict) -> list[str]:
    return [candidate["model"] for candidate in role["candidates"]]


def test_gpt_56_candidate_order_matches_policy() -> None:
    roles = _roles()

    assert _models(roles["general"]) == ["gpt-5.6-sol", "gpt-5.6-terra"]
    assert _models(roles["fast"]) == [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    ]
    assert _models(roles["coding"]) == [
        "gpt-5.6-codex",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    ]


def test_reasoning_roles_preserve_elevated_effort_on_fallback() -> None:
    roles = _roles()

    for name in ("reasoning", "research", "security-audit", "critical-ops"):
        assert _models(roles[name]) == ["gpt-5.6-sol", "gpt-5.6-terra"]
        assert [c["config"]["reasoning_effort"] for c in roles[name]["candidates"]] == [
            "high",
            "high",
        ]

    assert [c["config"]["reasoning_effort"] for c in roles["critique"]["candidates"]] == [
        "xhigh",
        "xhigh",
    ]
