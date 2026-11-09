"""Tests de backend/provenance.py: de dónde salió cada product_id.

La regla es de procedencia y no de existencia: un identificador que no apareció
en un resultado de esta conversación no se usa, exista o no en el catálogo.
"""

from __future__ import annotations

import pytest

from backend import provenance
from backend.tools import ToolArgumentError

KNOWN = {"MN-MON-0001", "MN-HDP-0001"}


def test_an_identifier_that_came_from_a_result_is_accepted() -> None:
    assert provenance.check_ids({"product_id": "MN-MON-0001"}, KNOWN) is None


def test_an_invented_identifier_is_rejected() -> None:
    # La falla reportada: el modelo armó 'MN-DOK-0001' por analogía.
    with pytest.raises(ToolArgumentError) as error:
        provenance.check_ids({"product_id": "MN-DOK-0001"}, KNOWN)

    assert "'MN-DOK-0001'" in str(error.value)
    assert "no salió de ninguna búsqueda de esta conversación" in str(error.value)


def test_the_rejection_says_to_search_by_name_first() -> None:
    with pytest.raises(ToolArgumentError) as error:
        provenance.check_ids({"product_id": "MN-DOK-0001"}, KNOWN)

    assert "search_products" in str(error.value)


def test_the_rejection_does_not_depend_on_the_product_existing() -> None:
    # MN-DOC-0029 existe en el catálogo real, y tampoco se acepta si no salió
    # de una búsqueda de esta conversación.
    with pytest.raises(ToolArgumentError) as error:
        provenance.check_ids({"product_id": "MN-DOC-0029"}, KNOWN)

    assert "exista o no en el catálogo" in str(error.value)


def test_nothing_is_known_at_the_start_of_a_conversation() -> None:
    with pytest.raises(ToolArgumentError):
        provenance.check_ids({"product_id": "MN-MON-0001"}, set())


def test_an_invocation_without_identifiers_passes() -> None:
    assert provenance.check_ids({"category": "Monitors"}, set()) is None


def test_every_identifier_of_a_comparison_is_checked() -> None:
    with pytest.raises(ToolArgumentError) as error:
        provenance.check_ids({"product_ids": ["MN-MON-0001", "MN-DOK-0001"]}, KNOWN)

    assert "'MN-DOK-0001'" in str(error.value)
    assert "MN-MON-0001" not in str(error.value)


def test_a_comparison_of_known_identifiers_passes() -> None:
    assert provenance.check_ids({"product_ids": sorted(KNOWN)}, KNOWN) is None


def test_the_identifiers_of_an_invocation_are_listed() -> None:
    assert provenance.requested_ids({"product_id": "MN-MON-0001"}) == ["MN-MON-0001"]


def test_the_identifiers_of_a_list_are_listed() -> None:
    arguments = {"product_ids": ["MN-MON-0001", "MN-HDP-0001"]}

    assert provenance.requested_ids(arguments) == ["MN-MON-0001", "MN-HDP-0001"]


def test_a_repeated_identifier_is_listed_once() -> None:
    arguments = {"product_ids": ["MN-MON-0001", "MN-MON-0001"]}

    assert provenance.requested_ids(arguments) == ["MN-MON-0001"]


def test_an_invocation_without_an_identifier_has_none() -> None:
    assert provenance.requested_ids({"category": "Monitors", "limit": 5}) == []


def test_the_identifier_of_a_search_result_is_collected() -> None:
    result = {"found": True, "products": [{"product_id": "MN-MON-0001", "name": "Nova"}]}

    assert provenance.collect_ids(result) == {"MN-MON-0001"}


def test_the_identifier_of_an_availability_result_is_collected() -> None:
    result = {"found": True, "product_id": "MN-MON-0001", "available_qty": 10}

    assert provenance.collect_ids(result) == {"MN-MON-0001"}


def test_the_identifier_of_a_sheet_is_collected() -> None:
    result = {"found": True, "product": {"product_id": "MN-MON-0001", "sku": "MON-10000"}}

    assert provenance.collect_ids(result) == {"MN-MON-0001"}


def test_the_identifiers_of_the_related_products_are_collected() -> None:
    # Vienen anidados: related[].product.product_id.
    result = {
        "found": True,
        "related": [
            {"relation_type": "alternative_to", "product": {"product_id": "MN-MON-0002"}},
            {"relation_type": "accessory_for", "product": {"product_id": "MN-HDP-0001"}},
        ],
    }

    assert provenance.collect_ids(result) == {"MN-MON-0002", "MN-HDP-0001"}


def test_the_identifiers_of_a_comparison_are_collected() -> None:
    result = {"products": [{"product_id": "MN-MON-0001"}, {"product_id": "MN-MON-0002"}]}

    assert provenance.collect_ids(result) == {"MN-MON-0001", "MN-MON-0002"}


def test_an_error_result_brings_no_identifiers() -> None:
    # Si la herramienta falló, el modelo no vio ningún producto.
    result = {"found": False, "error": "No existe el producto 'MN-NO-EXISTE'."}

    assert provenance.collect_ids(result) == set()


def test_an_empty_search_brings_no_identifiers() -> None:
    result = {"found": False, "total": 0, "products": [], "filters_used": {"category": "x"}}

    assert provenance.collect_ids(result) == set()
