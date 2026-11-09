"""Tests de backend/tools.py: las cinco herramientas sobre la base de prueba.

Son cinco: search_products, get_product_details, check_availability,
compare_products y get_related_products. El `lookup_product_name` que aparece en
la traza no es una herramienta del esquema —la corre el sistema antes del turno
y no se le ofrece al modelo— y se prueba en `test_product_lookup.py`.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend import catalog, catalog_text, tools


def test_searching_by_category_returns_the_products(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, category="Monitors")

    assert result["found"] is True
    assert {product["name"] for product in result["products"]} == {
        "Nova Vision 24",
        "Flux Vision 27",
    }


def test_searching_by_use_case_returns_the_products(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, recommended_for="office work")

    assert {product["name"] for product in result["products"]} == {
        "Nova Vision 24",
        "Nova Sound Pro",
    }


def test_a_search_without_results_says_so_explicitly(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, category="Monitors", max_price=1)

    assert result["found"] is False
    assert result["total"] == 0
    assert result["products"] == []
    assert "No hay productos" in result["message"]


def test_a_search_without_results_reports_the_filters_that_were_used(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, category="Monitors", max_price=1)

    assert result["filters_used"] == {"category": "Monitors", "max_price": 1}


def test_a_search_without_results_returns_the_valid_categories(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Filtros válidos que no traen nada juntos: el modelo tiene que poder saber
    # qué sacar en vez de rendirse.
    result = tools.search_products(catalog_connection, category="Monitors", max_price=1)

    assert result["valid_categories"] == ["Headphones", "Monitors"]


def test_a_search_without_results_returns_the_valid_use_cases(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(
        catalog_connection, recommended_for="gaming", max_price=1
    )

    assert "office work" in result["valid_recommended_for"]


def test_a_search_without_results_only_returns_what_could_be_wrong(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Lo que no se mandó no puede estar mal, y cada lista ocupa contexto.
    result = tools.search_products(catalog_connection, category="Monitors", max_price=1)

    assert "valid_recommended_for" not in result


def test_a_category_that_does_not_exist_is_rejected_before_searching(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.search_products(catalog_connection, category="Earphones")

    assert "'Earphones' no existe" in str(error.value)
    assert "Headphones, Monitors" in str(error.value)


def test_a_use_case_that_does_not_exist_is_rejected_before_searching(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.search_products(catalog_connection, recommended_for="video conferencing")

    assert "'video conferencing' no existe" in str(error.value)
    assert "office work" in str(error.value)


def test_a_use_case_of_another_category_is_rejected_before_searching(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Los dos valores existen pero la combinación no: antes devolvía cero.
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.search_products(
            catalog_connection, category="Headphones", recommended_for="gaming"
        )

    assert "'Headphones' no tiene productos para 'gaming'" in str(error.value)


def test_all_the_problems_of_the_filters_come_back_together(
    catalog_connection: sqlite3.Connection,
) -> None:
    # En CPU cada vuelta al modelo se siente: se entera de todo de una.
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.search_products(
            catalog_connection,
            category="Earphones",
            recommended_for="video conferencing",
            min_price=200,
            max_price=200,
        )

    message = str(error.value)
    assert "no pueden ser iguales" in message
    assert "'Earphones' no existe" in message
    assert "'video conferencing' no existe" in message


@pytest.mark.parametrize("category", ["headphones", "HEADPHONES", " Headphones "])
def test_a_valid_category_written_differently_is_accepted(
    catalog_connection: sqlite3.Connection, category: str
) -> None:
    # La búsqueda no distingue mayúsculas, así que la validación tampoco.
    assert tools.search_products(catalog_connection, category=category)["found"] is True


def test_a_search_without_results_warns_about_the_free_text(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, search="auriculares para videollamadas")

    assert "en inglés" in result["note_about_search"]


def test_a_search_that_finds_products_does_not_carry_the_vocabulary(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, category="Monitors")

    assert "valid_categories" not in result
    assert "filters_used" not in result


def test_the_reported_invocation_of_the_model_is_rejected(
    catalog_connection: sqlite3.Connection,
) -> None:
    # La llamada exacta que devolvía cero resultados: min_price == max_price,
    # un caso de uso que no existe y la frase del usuario en español.
    with pytest.raises(tools.ToolArgumentError):
        tools.search_products(
            catalog_connection,
            category="Headphones",
            max_price=200,
            min_price=200,
            recommended_for="video conferencing",
            search="auriculares para videollamadas",
            limit=5,
        )


@pytest.mark.parametrize("price", [0, 1, 200, 200.5])
def test_a_price_range_with_both_ends_equal_is_rejected(
    catalog_connection: sqlite3.Connection, price: float
) -> None:
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.search_products(catalog_connection, min_price=price, max_price=price)

    assert "no pueden ser iguales" in str(error.value)
    assert "solo max_price" in str(error.value)


def test_a_real_price_range_is_accepted(catalog_connection: sqlite3.Connection) -> None:
    result = tools.search_products(catalog_connection, min_price=100, max_price=500)

    assert result["found"] is True


@pytest.mark.parametrize(
    "filters", [{"max_price": 200}, {"min_price": 100}, {"min_price": None, "max_price": None}]
)
def test_a_single_price_end_is_accepted(
    catalog_connection: sqlite3.Connection, filters: dict[str, float | None]
) -> None:
    # Un tope solo, que es lo que quiso decir el usuario con "menos de 200".
    assert tools.search_products(catalog_connection, **filters)["found"] is True


def test_a_search_reports_the_total_without_paginating(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, limit=1)

    assert result["returned"] == 1
    assert result["total"] == 4


@pytest.mark.parametrize(
    ("limit", "expected"), [(0, 1), (-5, 1), (tools.MAX_SEARCH_LIMIT + 50, 4)]
)
def test_a_search_keeps_the_limit_inside_the_allowed_range(
    catalog_connection: sqlite3.Connection, limit: int, expected: int
) -> None:
    result = tools.search_products(catalog_connection, limit=limit)

    assert result["returned"] == expected


def test_a_search_returns_five_products_by_default() -> None:
    # Cada producto que devuelve lo tiene que leer el modelo, y eso cuesta
    # tiempo: el default es chico a propósito.
    assert tools.DEFAULT_SEARCH_LIMIT == 5


def test_a_search_only_returns_the_fields_the_model_needs(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, search="Nova Vision")

    assert set(result["products"][0]) == {
        "product_id",
        "name",
        "brand",
        "category",
        "currency",
        "current_price",
        "in_stock",
        "recommended_for",
        "not_recommended_for",
    }


# Cada herramienta con una invocación válida, para recorrer todos los resultados.
EVERY_TOOL = [
    ("search_products", {"category": "Headphones"}),
    ("get_product_details", {"product_id": "MN-HDP-0001"}),
    ("compare_products", {"product_ids": ["MN-HDP-0001", "MN-HDP-0002"]}),
    ("get_related_products", {"product_id": "MN-MON-0001"}),
]


# Busca una clave en cualquier parte de un resultado, por anidado que esté.
def contains_key(value: object, key: str) -> bool:
    """Dice si la clave aparece en el resultado, a cualquier profundidad."""
    if isinstance(value, dict):
        return key in value or any(contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, key) for item in value)
    return False


# Corre una herramienta por nombre, para los tests que recorren todas.
def result_of(
    connection: sqlite3.Connection, name: str, arguments: dict[str, object]
) -> dict[str, object]:
    """Devuelve el resultado de la herramienta."""
    return getattr(tools, name)(connection, **arguments)


@pytest.mark.parametrize(("name", "arguments"), EVERY_TOOL, ids=[t[0] for t in EVERY_TOOL])
def test_only_the_availability_tool_returns_a_quantity_of_stock(
    catalog_connection: sqlite3.Connection, name: str, arguments: dict[str, object]
) -> None:
    # Garantía del RF-07: con el número en cualquier otro resultado, el modelo
    # lo repite turnos después como si lo hubiera consultado de nuevo.
    assert not contains_key(result_of(catalog_connection, name, arguments), "available_qty")


@pytest.mark.parametrize(("name", "arguments"), EVERY_TOOL, ids=[t[0] for t in EVERY_TOOL])
def test_every_tool_says_whether_there_is_stock(
    catalog_connection: sqlite3.Connection, name: str, arguments: dict[str, object]
) -> None:
    assert contains_key(result_of(catalog_connection, name, arguments), "in_stock")


def test_the_availability_tool_is_the_one_that_gives_the_quantity(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-MON-0001")

    assert result["available_qty"] == 10


def test_the_sheet_says_whether_there_is_stock_without_the_quantity(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_product_details(catalog_connection, "MN-MON-0001")

    assert result["product"]["in_stock"] is True
    assert "available_qty" not in result["product"]


def test_comparing_says_whether_there_is_stock_without_the_quantity(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Por acá salió el "7 unidades" sin consultar nada.
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-MON-0002"])

    assert [product["in_stock"] for product in result["products"]] == [
        catalog_text.IN_STOCK,
        catalog_text.OUT_OF_STOCK,
    ]


def test_comparing_never_sends_a_raw_boolean_for_the_stock(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Con un true/false el modelo escribió "Stock: 1 unidad disponible" para un
    # producto con 29 unidades: tenía un booleano y elaboró un número. Este test
    # falla si vuelve a viajar un booleano crudo en un producto comparado.
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-MON-0002"])

    for product in result["products"]:
        booleans = {key for key, value in product.items() if isinstance(value, bool)}
        assert booleans == set()


def test_the_related_products_say_whether_there_is_stock_without_the_quantity(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(catalog_connection, "MN-MON-0001")

    assert result["related"][0]["product"]["in_stock"] in (True, False)
    assert "available_qty" not in result["related"][0]["product"]


def test_a_search_says_whether_there_is_stock_but_not_how_much(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Garantía del RF-07: afirmó "7 unidades" con el dato de un search anterior.
    result = tools.search_products(catalog_connection, search="Nova Vision 24")

    assert result["products"][0]["in_stock"] is True
    assert "available_qty" not in result["products"][0]


def test_a_search_reports_a_product_without_stock(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, search="Flux Vision 27")

    assert result["products"][0]["in_stock"] is False


@pytest.mark.parametrize(
    "field", ["available_qty", "sku", "image_url", "tags", "description", "specifications"]
)
def test_a_search_does_not_send_the_model_what_it_does_not_need(
    catalog_connection: sqlite3.Connection, field: str
) -> None:
    result = tools.search_products(catalog_connection, search="Nova Vision")

    assert field not in result["products"][0]


def test_a_search_brings_what_the_product_is_not_recommended_for(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Sin este campo el asistente no puede avisar que el producto no sirve para
    # lo que el usuario quiere hacer.
    result = tools.search_products(catalog_connection, search="Nova Vision")

    assert result["products"][0]["not_recommended_for"] == "gaming"


def test_a_search_keeps_the_price(catalog_connection: sqlite3.Connection) -> None:
    result = tools.search_products(catalog_connection, search="Nova Vision 24")

    assert result["products"][0]["current_price"] == 468.62


def test_the_details_still_bring_the_whole_sheet(
    catalog_connection: sqlite3.Connection,
) -> None:
    # El recorte es solo de la búsqueda: para un producto puntual va la ficha.
    result = tools.get_product_details(catalog_connection, "MN-MON-0001")

    assert result["product"]["tags"] == "monitor; display; qhd"
    assert result["product"]["sku"] == "MON-10000"


def test_a_search_brings_the_use_case_to_justify_the_recommendation(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, search="Nova Vision")

    assert result["products"][0]["recommended_for"] == "office work; programming"


def test_the_details_bring_the_specifications(catalog_connection: sqlite3.Connection) -> None:
    result = tools.get_product_details(catalog_connection, "MN-MON-0001")

    assert result["found"] is True
    assert len(result["product"]["specifications"]) == 2


def test_the_details_keep_the_literal_none_of_a_specification(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_product_details(catalog_connection, "MN-HDP-0001")

    values = {
        specification["attribute_name"]: specification["value"]
        for specification in result["product"]["specifications"]
    }
    # "None" significa que el producto no tiene la característica, y la pantalla
    # lo imprime como "No": al modelo le llega lo mismo.
    assert values["Water Resistance"] == catalog_text.NO_FEATURE


def test_the_details_write_a_specification_that_is_zero_with_its_unit(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Lo que ve el modelo tiene que decir "0 h", no un 0 suelto: tres rondas
    # con la regla en el prompt y el 0 lo seguía leyendo como ausencia de dato.
    result = tools.get_product_details(catalog_connection, "MN-HDP-0001")

    battery = next(
        item
        for item in result["product"]["specifications"]
        if item["attribute_name"] == "Battery Life"
    )
    assert battery["value"] == "0 h"


def test_the_details_do_not_carry_the_raw_number_of_a_specification(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Si el número viaja al lado del texto, sigue estando el 0 suelto.
    result = tools.get_product_details(catalog_connection, "MN-HDP-0001")

    for specification in result["product"]["specifications"]:
        assert "value_number" not in specification
        assert "value_text" not in specification


def test_comparing_writes_a_specification_that_is_zero_with_its_unit(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-HDP-0001", "MN-HDP-0002"])

    battery = next(
        item
        for item in result["shared_specifications"]
        if item["attribute_name"] == "Battery Life"
    )
    # Es lo mismo que imprime la tabla de comparación.
    assert battery["values"]["MN-HDP-0001"]["value"] == "0 h"
    assert battery["values"]["MN-HDP-0002"]["value"] == "26 h"


def test_comparing_hangs_the_product_name_from_each_value(
    catalog_connection: sqlite3.Connection,
) -> None:
    # El modelo escribe la prosa con el nombre, no con el product_id: al
    # traducirlo le puso a un producto la conectividad y el formato del otro.
    result = tools.compare_products(catalog_connection, ["MN-HDP-0001", "MN-HDP-0002"])

    battery = next(
        item
        for item in result["shared_specifications"]
        if item["attribute_name"] == "Battery Life"
    )
    assert battery["values"]["MN-HDP-0001"]["name"] == "Nova Sound Pro"
    assert battery["values"]["MN-HDP-0002"]["name"] == "Flux Buds"


def test_the_name_of_a_value_is_the_one_of_its_own_product(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Si el nombre no es el del dueño del valor, esto empeora el problema en vez
    # de arreglarlo.
    result = tools.compare_products(catalog_connection, ["MN-HDP-0001", "MN-HDP-0002"])

    names = {product["product_id"]: product["name"] for product in result["products"]}
    for specification in result["shared_specifications"]:
        for product_id, value in specification["values"].items():
            assert value["name"] == names[product_id]


def test_comparing_writes_an_empty_use_case_field(
    catalog_connection: sqlite3.Connection,
) -> None:
    # El campo que en rondas anteriores el modelo completaba con el valor de
    # otro producto.
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-MON-0002"])

    uses = {
        product["name"]: product["not_recommended_for"] for product in result["products"]
    }
    assert uses["Nova Vision 24"] == "gaming"
    assert uses["Flux Vision 27"] == catalog_text.MISSING_USES


def test_a_search_writes_an_empty_use_case_field(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.search_products(catalog_connection, category="Monitors")

    uses = {
        product["name"]: product["not_recommended_for"] for product in result["products"]
    }
    assert uses["Flux Vision 27"] == catalog_text.MISSING_USES


def test_the_details_write_an_empty_use_case_field(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_product_details(catalog_connection, "MN-MON-0002")

    assert result["product"]["not_recommended_for"] == catalog_text.MISSING_USES


def test_a_related_product_never_brings_a_use_case_field_in_null(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Todos los relacionados pasan por catalog_text, igual que los de una
    # búsqueda: el hueco es el mismo de donde el modelo copiaba otro valor.
    result = tools.get_related_products(catalog_connection, "MN-MON-0001")

    for item in result["related"]:
        assert isinstance(item["product"]["recommended_for"], str)


def test_the_details_report_a_missing_price_as_null(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_product_details(catalog_connection, "MN-HDP-0003")

    assert result["product"]["current_price"] is None


def test_the_availability_adds_up_the_warehouses(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-MON-0001")

    assert result["available_qty"] == 10
    assert result["in_stock"] is True
    assert "10 unidades" in result["message"]


@pytest.mark.parametrize(
    ("available", "expected"),
    [
        (1, "Nova Vision 24: hay 1 unidad disponible."),
        (2, "Nova Vision 24: hay 2 unidades disponibles."),
    ],
)
def test_the_message_of_the_stock_agrees_in_number(available: int, expected: str) -> None:
    # El modelo repite este texto casi literal: "1 unidades" lo lee el usuario.
    assert tools.stock_message("Nova Vision 24", available) == expected


def test_the_message_without_stock_does_not_say_a_number() -> None:
    assert tools.stock_message("Nova Vision 24", 0) == (
        "Nova Vision 24: no hay stock disponible en ningún depósito."
    )


@pytest.mark.parametrize("available", [0, 1, 7])
def test_the_message_of_the_stock_names_its_product(available: int) -> None:
    # Sin el nombre, el modelo le puso "7 unidades disponibles" a dos productos
    # a la vez: el número era de uno y la frase no decía de cuál.
    assert tools.stock_message("Aether Sound 880", available).startswith(
        "Aether Sound 880:"
    )


def test_the_availability_message_names_the_product_that_was_consulted(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-MON-0001")

    assert result["message"] == "Nova Vision 24: hay 10 unidades disponibles."


def test_the_availability_of_a_product_without_stock_says_there_is_none(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-MON-0002")

    assert result["available_qty"] == 0
    assert result["in_stock"] is False
    assert result["message"] == "Flux Vision 27: no hay stock disponible en ningún depósito."


def test_the_availability_of_a_product_without_inventory_is_zero(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.check_availability(catalog_connection, "MN-HDP-0003")

    assert result["available_qty"] == 0
    assert result["in_stock"] is False


def test_comparing_two_products_returns_their_comparable_data(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-HDP-0001"])

    assert [product["name"] for product in result["products"]] == [
        "Nova Vision 24",
        "Nova Sound Pro",
    ]
    assert result["products"][0]["current_price"] == 468.62


def test_comparing_products_only_uses_the_shared_specifications(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-HDP-0001"])

    # No comparten ningún atributo: uno tiene Display y el otro Audio.
    assert result["shared_specifications"] == []


def test_comparing_products_keeps_the_value_of_each_one(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-MON-0002"])

    assert result["products"][1]["current_price"] == 700.0


@pytest.mark.parametrize("product_ids", [[], ["MN-MON-0001"], "MN-MON-0001"])
def test_comparing_less_than_two_products_is_rejected(
    catalog_connection: sqlite3.Connection, product_ids: object
) -> None:
    # Con uno no hay nada que enfrentar: es lo único que sigue siendo un error.
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.compare_products(catalog_connection, product_ids)

    assert f"al menos {tools.MIN_COMPARE} product_id" in str(error.value)


def test_the_rejection_says_that_the_identifiers_are_not_asked_to_the_user(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(tools.ToolArgumentError) as error:
        tools.compare_products(catalog_connection, ["MN-MON-0001"])

    assert str(error.value).startswith("Volvé a invocar compare_products")
    assert "no se le preguntan al usuario" in str(error.value)


FIVE_PRODUCTS = [
    "MN-MON-0001",
    "MN-MON-0002",
    "MN-HDP-0001",
    "MN-HDP-0002",
    "MN-HDP-0003",
]


def test_comparing_more_than_the_limit_compares_the_first_ones(
    catalog_connection: sqlite3.Connection,
) -> None:
    # Un rechazo obliga al modelo a corregirse, y cuando no puede termina
    # pidiéndole al usuario que elija identificadores.
    result = tools.compare_products(catalog_connection, FIVE_PRODUCTS)

    assert result["found"] is True
    assert len(result["products"]) == tools.MAX_COMPARE
    assert result["compared"] == FIVE_PRODUCTS[: tools.MAX_COMPARE]


def test_the_comparison_says_which_products_were_left_out(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, FIVE_PRODUCTS)

    assert result["left_out"] == ["MN-HDP-0002", "MN-HDP-0003"]
    assert "quedaron afuera MN-HDP-0002, MN-HDP-0003" in result["note"]


def test_the_note_says_what_to_do_with_the_ones_left_out(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, FIVE_PRODUCTS)

    assert "volvé a invocar con ellos" in result["note"]


def test_a_comparison_within_the_limit_has_no_note(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.compare_products(catalog_connection, ["MN-MON-0001", "MN-MON-0002"])

    assert "note" not in result
    assert "left_out" not in result


def test_the_related_products_come_ordered_by_strength(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(catalog_connection, "MN-MON-0001")

    strengths = [item["strength"] for item in result["related"]]
    assert strengths == sorted(strengths, reverse=True)


def test_the_related_products_can_be_filtered_by_type(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(
        catalog_connection, "MN-MON-0001", relation_type="accessory_for"
    )

    assert result["count"] == 1
    assert result["related"][0]["product"]["name"] == "Nova Sound Pro"


def test_a_product_without_relations_says_so_explicitly(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(catalog_connection, "MN-HDP-0003")

    assert result["found"] is False
    assert result["related"] == []
    assert "no tiene productos relacionados" in result["message"]


def test_a_relation_type_without_results_says_so_explicitly(
    catalog_connection: sqlite3.Connection,
) -> None:
    result = tools.get_related_products(
        catalog_connection, "MN-MON-0002", relation_type="accessory_for"
    )

    assert result["found"] is False
    assert "accessory_for" in result["message"]


def test_there_is_no_tool_to_list_the_categories() -> None:
    # Viajan en el enum de search_products: pedirlas aparte no aporta nada y
    # ocupa contexto en cada turno.
    assert not hasattr(tools, "list_categories")


def test_a_product_that_does_not_exist_is_not_invented(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(catalog.ProductNotFoundError):
        tools.get_product_details(catalog_connection, "MN-NO-EXISTE")


def test_the_availability_of_a_product_that_does_not_exist_is_not_invented(
    catalog_connection: sqlite3.Connection,
) -> None:
    with pytest.raises(catalog.ProductNotFoundError):
        tools.check_availability(catalog_connection, "MN-NO-EXISTE")
