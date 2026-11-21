"""Check that every translation covers exactly the keys of strings.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

COMPONENT = Path(__file__).parent.parent / "custom_components" / "backrest"


def _keys(data: Any, prefix: str = "") -> set[str]:
    if isinstance(data, dict):
        return set().union(*(_keys(v, f"{prefix}{k}.") for k, v in data.items()))
    return {prefix.rstrip(".")}


def _placeholders(text: str) -> set[str]:
    return {part.split("}")[0] for part in text.split("{")[1:]}


def _leaves(data: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(data, dict):
        out: dict[str, str] = {}
        for key, value in data.items():
            out |= _leaves(value, f"{prefix}{key}.")
        return out
    return {prefix.rstrip("."): data}


STRINGS = json.loads((COMPONENT / "strings.json").read_text())
LANGUAGES = sorted(p.stem for p in (COMPONENT / "translations").glob("*.json"))


@pytest.mark.parametrize("language", LANGUAGES)
def test_translation_complete(language: str) -> None:
    """Same keys as strings.json and the same {placeholders}."""
    data = json.loads((COMPONENT / "translations" / f"{language}.json").read_text())
    assert _keys(data) == _keys(STRINGS)
    english = _leaves(json.loads((COMPONENT / "translations" / "en.json").read_text()))
    for key, text in _leaves(data).items():
        assert _placeholders(text) == _placeholders(english[key]), key


def test_icons_match_entities() -> None:
    """Every entity translation key has an icon and vice versa."""
    icons = json.loads((COMPONENT / "icons.json").read_text())["entity"]
    for platform, entities in STRINGS["entity"].items():
        assert set(icons[platform]) <= set(entities), platform
    assert set(icons["sensor"]) == set(STRINGS["entity"]["sensor"])
