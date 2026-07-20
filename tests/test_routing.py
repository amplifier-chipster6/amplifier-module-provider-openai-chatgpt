"""Contract tests for the shipped OpenAI ChatGPT routing policy."""

from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
ROUTING_PATH = ROOT / "routing" / "openai-chatgpt.yaml"
README_PATH = ROOT / "README.md"

EXPECTED_ROLES = {
    "general",
    "fast",
    "ui-coding",
    "creative",
    "writing",
    "vision",
    "image-gen",
    "coding",
    "reasoning",
    "security-audit",
    "research",
    "critical-ops",
    "critique",
}

FULL_CATALOG = [
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.5-codex",
]
PARTIAL_CATALOG = ["gpt-5.6-terra", "gpt-5.5"]
EMERGENCY_CATALOG = ["gpt-5.5"]


@pytest.fixture(scope="module")
def routing() -> dict[str, Any]:
    """Load the exact routing policy shipped by this repository."""
    return yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8"))


def _candidate_pairs(role: dict[str, Any]) -> list[tuple[str, str | None]]:
    return [
        (candidate["model"], candidate.get("config", {}).get("reasoning_effort"))
        for candidate in role["candidates"]
    ]


def _resolve(role: dict[str, Any], catalog: list[str]) -> tuple[str, dict[str, Any]]:
    """Resolve the first routing candidate present in a synthetic catalog."""
    for candidate in role["candidates"]:
        for model in catalog:
            if fnmatchcase(model, candidate["model"]):
                return model, candidate.get("config", {})
    raise AssertionError(f"No candidate resolved from catalog: {catalog}")


def test_policy_defines_exactly_thirteen_roles(routing: dict[str, Any]) -> None:
    assert set(routing["roles"]) == EXPECTED_ROLES


def test_candidate_order_and_reasoning_effort_are_explicit(
    routing: dict[str, Any],
) -> None:
    roles = routing["roles"]
    general = [
        ("gpt-5.6-sol", None),
        ("gpt-5.6-terra", None),
        ("gpt-5.6-luna", None),
        ("gpt-5.*", None),
    ]
    fast = [
        ("gpt-5.6-luna", None),
        ("gpt-5.6-terra", None),
        ("gpt-5.6-sol", None),
        ("gpt-5.*", None),
    ]
    coding = [
        ("gpt-?.?-codex*", None),
        ("gpt-5.6-terra", None),
        ("gpt-5.6-sol", None),
        ("gpt-5.*", None),
    ]
    reasoning = [
        ("gpt-5.6-sol", "high"),
        ("gpt-5.6-terra", "high"),
        ("gpt-5.*", None),
    ]
    critique = [
        ("gpt-5.6-sol", "max"),
        ("gpt-5.6-terra", "xhigh"),
        ("gpt-5.*", None),
    ]

    for role in ("general", "ui-coding", "creative", "writing", "vision", "image-gen"):
        assert _candidate_pairs(roles[role]) == general
    assert _candidate_pairs(roles["fast"]) == fast
    assert _candidate_pairs(roles["coding"]) == coding
    for role in ("reasoning", "security-audit", "research", "critical-ops"):
        assert _candidate_pairs(roles[role]) == reasoning
    assert _candidate_pairs(roles["critique"]) == critique


def test_policy_never_invents_a_gpt_5_6_codex_id(routing: dict[str, Any]) -> None:
    models = {
        candidate["model"]
        for role in routing["roles"].values()
        for candidate in role["candidates"]
    }
    assert "gpt-5.6-codex" not in models


@pytest.mark.parametrize(
    ("catalog", "expected"),
    [
        (
            FULL_CATALOG,
            {
                "general": "gpt-5.6-sol",
                "fast": "gpt-5.6-luna",
                "ui-coding": "gpt-5.6-sol",
                "creative": "gpt-5.6-sol",
                "writing": "gpt-5.6-sol",
                "vision": "gpt-5.6-sol",
                "image-gen": "gpt-5.6-sol",
                "coding": "gpt-5.5-codex",
                "reasoning": "gpt-5.6-sol",
                "security-audit": "gpt-5.6-sol",
                "research": "gpt-5.6-sol",
                "critical-ops": "gpt-5.6-sol",
                "critique": "gpt-5.6-sol",
            },
        ),
        (PARTIAL_CATALOG, {role: "gpt-5.6-terra" for role in EXPECTED_ROLES}),
        (EMERGENCY_CATALOG, {role: "gpt-5.5" for role in EXPECTED_ROLES}),
    ],
)
def test_all_roles_resolve_against_staged_catalogs(
    routing: dict[str, Any], catalog: list[str], expected: dict[str, str]
) -> None:
    resolved = {
        role: _resolve(policy, catalog)[0] for role, policy in routing["roles"].items()
    }
    assert resolved == expected


def test_reasoning_effort_follows_selected_candidate(
    routing: dict[str, Any],
) -> None:
    roles = routing["roles"]
    assert _resolve(roles["reasoning"], FULL_CATALOG) == (
        "gpt-5.6-sol",
        {"reasoning_effort": "high"},
    )
    assert _resolve(roles["critique"], PARTIAL_CATALOG) == (
        "gpt-5.6-terra",
        {"reasoning_effort": "xhigh"},
    )
    assert _resolve(roles["reasoning"], EMERGENCY_CATALOG) == ("gpt-5.5", {})


def test_readme_routing_rationale_matches_policy() -> None:
    readme = " ".join(README_PATH.read_text(encoding="utf-8").split())
    required_statements = (
        "General and quality-first roles prefer Sol",
        "Fast work prefers Luna",
        "Coding prefers a catalog-provided Codex model",
        "Explicit `request.model` always wins",
        "candidate order is this repository's policy",
    )
    for statement in required_statements:
        assert statement in readme
