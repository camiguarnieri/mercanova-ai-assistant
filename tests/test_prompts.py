"""Tests de backend/prompts.py: que las reglas obligatorias estén en el prompt."""

from __future__ import annotations

import re

import pytest

from backend import prompts


@pytest.mark.parametrize(
    "rule",
    [
        # Nunca afirmar un dato sin consultarlo.
        "no inventás datos",
        "en esta misma conversación",
        "decí que no lo tenés",
        "no lo estimes, no lo",
        # product_id solo si vino de una herramienta.
        "product_id",
        # Consultar de nuevo antes de afirmar precio o disponibilidad.
        "consultalos de nuevo",
    ],
)
def test_the_prompt_forbids_inventing_data(rule: str) -> None:
    # Sin distinguir mayúsculas: la regla puede caer al principio de una oración.
    assert rule.lower() in prompts.SYSTEM_PROMPT.lower()


@pytest.mark.parametrize(
    "rule",
    ["Respondé siempre en español", "el catálogo está en inglés", "antes de buscar"],
)
def test_the_prompt_explains_the_language_of_the_catalog(rule: str) -> None:
    assert rule in prompts.SYSTEM_PROMPT


def test_the_prompt_explains_that_none_is_a_value() -> None:
    assert 'el texto "None" es un valor real' in prompts.SYSTEM_PROMPT
    assert "NO tiene esa característica" in prompts.SYSTEM_PROMPT


def test_the_prompt_distinguishes_none_from_a_missing_value() -> None:
    assert "distinto de que falte el dato" in prompts.SYSTEM_PROMPT


def test_the_prompt_asks_to_question_before_recommending() -> None:
    assert "preguntá antes de recomendar" in prompts.SYSTEM_PROMPT


def test_the_prompt_asks_to_justify_with_recommended_for() -> None:
    assert "recommended_for" in prompts.SYSTEM_PROMPT


def test_the_prompt_mentions_the_stock_before_recommending() -> None:
    assert "available_qty" in prompts.SYSTEM_PROMPT


def test_the_prompt_does_not_carry_catalog_data() -> None:
    # El catálogo se consulta con herramientas, no se mete en el prompt.
    assert re.search(r"MN-[A-Z]{3}-\d{4}", prompts.SYSTEM_PROMPT) is None
    assert "USD" not in prompts.SYSTEM_PROMPT


def test_the_prompt_has_no_prices() -> None:
    assert re.search(r"\d+[.,]\d{2}", prompts.SYSTEM_PROMPT) is None


def test_building_the_prompt_without_extras_returns_the_base_one() -> None:
    assert prompts.build_system_prompt() == prompts.SYSTEM_PROMPT


@pytest.mark.parametrize("extra", [None, "", "   "])
def test_an_empty_extra_does_not_change_the_prompt(extra: str | None) -> None:
    assert prompts.build_system_prompt(extra) == prompts.SYSTEM_PROMPT


def test_an_extra_instruction_is_appended_at_the_end() -> None:
    result = prompts.build_system_prompt("El usuario ya eligió un monitor.")

    assert result.startswith(prompts.SYSTEM_PROMPT)
    assert result.endswith("El usuario ya eligió un monitor.")
