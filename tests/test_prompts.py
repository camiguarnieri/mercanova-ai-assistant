"""Tests de backend/prompts.py: que las reglas obligatorias estén en el prompt.

El prompt se escribió apretado para que entre en el contexto de un modelo chico,
así que acá se verifica que al apretarlo no se haya caído ninguna regla. Las
reglas se buscan sobre el texto con los saltos de línea normalizados: lo que
importa es que la regla esté, no en qué columna se cortó.
"""

from __future__ import annotations

import re

import pytest

from backend import prompts

# El prompt viaja en cada pedido al modelo, que corre en CPU: si crece, el
# usuario espera más. Aproximado como len/4, que es la medida con la que se
# viene comparando.
#
# El tope no es por contexto —con num_ctx en 8192 sobra lugar— sino por el techo
# de instrucciones del modelo. Se midió el tamaño contra el comportamiento en
# cinco rondas: 698, 893, 898, 899 y 1164 tokens, y en la de 1164 el modelo
# ignoró la regla nueva, dejó de llamar herramientas en dos turnos e inventó dos
# productos que no existen. Cada regla que entra de acá en adelante tiene que
# sacar otra, o resolverse en código.
MAX_PROMPT_TOKENS = 900

# El mismo texto en una sola línea, para buscar una regla sin depender del corte.
PROMPT = " ".join(prompts.SYSTEM_PROMPT.split())


def test_the_prompt_fits_in_the_context_budget() -> None:
    assert len(prompts.SYSTEM_PROMPT) // 4 < MAX_PROMPT_TOKENS


@pytest.mark.parametrize(
    "rule",
    [
        # Nunca afirmar un dato sin consultarlo en esta conversación.
        "NO INVENTES DATOS",
        "que no hayas obtenido de una herramienta en esta conversación",
        # Si falta el dato, decirlo en vez de completarlo.
        "si no lo tenés, decilo, no lo estimes",
        "ni uses lo que sepas de la marca",
        # El product_id solo si vino de una herramienta.
        "Un product_id se usa solo si vino de una herramienta",
        # Los precios como están en el catálogo.
        "sin convertir ni redondear",
    ],
)
def test_the_prompt_forbids_inventing_data(rule: str) -> None:
    assert rule in PROMPT


def test_the_prompt_asks_for_every_sheet_before_comparing_a_feature() -> None:
    # Afirmó la batería de un producto cuya ficha nunca consultó.
    assert "Si comparás una característica entre productos" in PROMPT
    assert "pedí la ficha de cada uno o usá compare_products" in PROMPT


def test_the_prompt_says_the_quantity_only_comes_from_the_availability_tool() -> None:
    # Afirmó "7 unidades" con el dato del search del turno anterior.
    assert "search_products dice si hay stock, no cuántas unidades" in PROMPT
    assert "la cantidad sale de check_availability" in PROMPT


def test_the_prompt_forbids_naming_a_specification_that_was_not_consulted() -> None:
    # Ofreció "tiempo de carga" y "capacidad total", que no existen.
    assert "No nombres ni ofrezcas una especificación que no haya salido de un resultado" in (
        PROMPT
    )


def test_the_prompt_forbids_moving_a_value_from_one_product_to_another() -> None:
    # Le pegó el not_recommended_for de otro producto al Aether Sound 880.
    assert "Cada valor pertenece al producto del que salió" in PROMPT
    assert "ni completes el campo vacío de uno con el de otro" in PROMPT


def test_the_prompt_forbids_a_superlative_without_ordering() -> None:
    # Dijo que 182.94 y 165.82 eran "los más baratos" de los tres.
    assert 'No digas "el más barato", "el mejor" ni "el que más dura"' in PROMPT
    assert "sin haber ordenado los valores que recibiste" in PROMPT


@pytest.mark.parametrize(
    "rule",
    [
        # Si nombra un producto, el sistema ya lo buscó: hay que usar el dato.
        "Si el usuario nombra un producto, el sistema ya lo buscó",
        "Nunca afirmes que un producto no está en el catálogo sin ese respaldo",
        # Precio y stock de algo ya mostrado se vuelven a consultar.
        "se contesta consultando de nuevo, aunque el dato haya aparecido antes",
        # Una característica se consulta en vez de preguntar.
        "consultala en vez de preguntarle a cuál se refiere",
    ],
)
def test_the_prompt_says_when_the_catalog_has_to_be_consulted(rule: str) -> None:
    assert rule in PROMPT


def test_the_prompt_separates_when_to_consult_from_when_not_to() -> None:
    # La regla positiva es la que faltaba: las otras eran todas restrictivas.
    assert "CUÁNDO SÍ, SIEMPRE:" in PROMPT
    assert "CUÁNDO NO:" in PROMPT


@pytest.mark.parametrize(
    "rule",
    [
        "respondé en español",
        "el catálogo está en inglés",
        "traducí la necesidad a filtros en inglés",
        "van sin traducir",
    ],
)
def test_the_prompt_explains_the_language_of_the_catalog(rule: str) -> None:
    assert rule in PROMPT


def test_the_prompt_gives_an_example_of_the_translation() -> None:
    assert 'es category "Headphones" y recommended_for "travel"' in PROMPT


@pytest.mark.parametrize(
    "rule",
    [
        # Un saludo se contesta sin consultar nada.
        "Un saludo, un gracias, una despedida",
        "contestan sin ninguna",
        'a "hola", preguntá qué necesita, no busques',
    ],
)
def test_the_prompt_asks_to_consult_only_when_it_is_needed(rule: str) -> None:
    assert rule in PROMPT


def test_the_prompt_asks_not_to_drag_the_previous_message() -> None:
    # Al contestar "hola" ofrecía seguir con la búsqueda fallida anterior.
    assert "Contestá cada mensaje por lo que pide" in PROMPT
    assert "sin arrastrar lo que ofreciste antes" in PROMPT


def test_the_prompt_asks_not_to_add_a_filter_the_user_did_not_mention() -> None:
    # Buscó con recommended_for='content creation' sin que el usuario lo dijera.
    assert "Los filtros salen de lo que dijo el usuario" in PROMPT
    assert "no agregues un caso de uso, marca ni precio que no mencionó" in PROMPT


@pytest.mark.parametrize(
    "rule",
    [
        # Los opcionales se omiten en vez de mandarse vacíos.
        "Omití los opcionales que no uses",
        'con la palabra "null" ni vacíos',
        # Los números van sin comillas.
        "sin comillas",
    ],
)
def test_the_prompt_explains_how_to_send_the_optional_arguments(rule: str) -> None:
    assert rule in PROMPT


def test_the_prompt_sends_the_model_to_read_the_schema_of_each_parameter() -> None:
    # Qué valores acepta cada filtro y cuándo se usa está en el esquema, que es
    # lo que el modelo lee mientras arma la invocación: acá no se repite.
    assert "Cada parámetro dice en el esquema qué valores acepta y cuándo se usa" in PROMPT


@pytest.mark.parametrize(
    "rule",
    [
        "min_price",
        "max_price",
        "search es para",
        "category y recommended_for",
    ],
)
def test_the_prompt_does_not_repeat_what_the_schema_already_says(rule: str) -> None:
    # Las reglas de cada parámetro viven en tool_schemas.py y se verifican allá.
    assert PROMPT.count(rule) <= 1


def test_the_prompt_asks_to_retry_before_giving_up() -> None:
    assert "te dice qué corregir: arreglalo y buscá otra vez" in PROMPT


def test_the_prompt_explains_that_none_is_a_value() -> None:
    assert 'El texto "None" es un valor real' in PROMPT
    assert "NO tiene esa característica" in PROMPT


def test_the_prompt_distinguishes_none_from_a_missing_value() -> None:
    assert '"No hay información" se dice solo si el campo no vino' in PROMPT


def test_the_prompt_says_that_a_zero_is_a_value() -> None:
    # 80 especificaciones del catálogo tienen value_number = 0 y el modelo
    # contestaba "no hay especificación disponible".
    assert "Un value_number en 0 también es un dato real" in PROMPT
    assert "reportalo como 0 con su unidad" in PROMPT


def test_the_prompt_explains_where_the_value_of_a_specification_is() -> None:
    assert "value_text o en value_number, nunca en las dos" in PROMPT
    assert "la unidad va en unit" in PROMPT


def test_the_prompt_asks_to_question_before_recommending() -> None:
    assert "preguntá antes de buscar, una cosa por vez" in PROMPT


def test_the_prompt_asks_to_question_when_only_a_category_was_named() -> None:
    # A "quiero una notebook" devolvió cinco notebooks sin preguntar nada.
    assert "nombró solo una categoría sin uso, presupuesto ni característica" in PROMPT


def test_the_prompt_gives_an_example_of_an_ambiguous_need() -> None:
    assert 'a "quiero una notebook", para qué la va a usar' in PROMPT


def test_the_prompt_asks_not_to_question_more_than_needed() -> None:
    assert "Si ya tenés con qué, recomendá sin preguntar más" in PROMPT


def test_the_prompt_asks_to_justify_with_recommended_for() -> None:
    assert "Explicá por qué le sirve con su recommended_for" in PROMPT


def test_the_prompt_mentions_the_price_and_the_stock_that_were_consulted() -> None:
    assert "el precio y el stock que consultaste" in PROMPT


def test_the_prompt_does_not_ask_for_a_field_the_model_no_longer_receives() -> None:
    # not_recommended_for dejó de viajar al modelo (backend/model_view.py):
    # pedirle que lo use sería mandarlo a buscar un campo que no está.
    assert "not_recommended_for" not in PROMPT


def test_the_prompt_forbids_explaining_the_cause_of_a_value() -> None:
    # Con "0 h" dijo "es una opción sin batería" y "dependen de un cargador
    # externo". El catálogo da el valor, no la causa.
    assert "Reportá el valor y nada más" in PROMPT
    assert "no expliques por qué ni qué implica" in PROMPT


def test_the_prompt_asks_to_warn_when_there_is_no_stock() -> None:
    assert "Si in_stock es false, avisalo y ofrecé una alternativa" in PROMPT


def test_the_prompt_does_not_name_a_field_that_the_search_no_longer_returns() -> None:
    # search_products ya no devuelve available_qty: nombrarlo acá le haría
    # buscar un campo que no está en el resultado.
    assert "available_qty" not in PROMPT


def test_the_prompt_limits_how_many_products_are_recommended() -> None:
    assert "Máximo tres productos por respuesta" in PROMPT


def test_the_prompt_does_not_repeat_a_rule_in_two_blocks() -> None:
    # Al apretarlo se juntó en una sola línea lo que antes estaba dicho en dos
    # bloques: qué hacer cuando una herramienta no trae nada.
    assert PROMPT.count("no hay nada") == 1
    assert PROMPT.count("ofrecé otra búsqueda") == 0


def test_every_block_of_the_prompt_appears_once() -> None:
    headers = ["NO INVENTES DATOS", "IDIOMA", "HERRAMIENTAS", "ARGUMENTOS", "RECOMENDAR"]

    assert [PROMPT.count(header) for header in headers] == [1, 1, 1, 1, 1]


def test_the_prompt_does_not_carry_the_vocabulary_of_the_catalog() -> None:
    # Los valores válidos viajan en el esquema, que se arma desde la base. Si se
    # escribieran acá, quedarían viejos al cargar otro dataset.
    for value in ("Docking Stations", "External Storage", "laptop expansion"):
        assert value not in PROMPT


def test_the_prompt_does_not_mention_a_tool_that_does_not_exist() -> None:
    assert "list_categories" not in PROMPT


def test_the_prompt_does_not_carry_catalog_data() -> None:
    # El catálogo se consulta con herramientas, no se mete en el prompt.
    assert re.search(r"MN-[A-Z]{3}-\d{4}", PROMPT) is None
    assert "USD" not in PROMPT


def test_the_prompt_has_no_prices() -> None:
    assert re.search(r"\d+[.,]\d{2}", PROMPT) is None


def test_building_the_prompt_without_extras_returns_the_base_one() -> None:
    assert prompts.build_system_prompt() == prompts.SYSTEM_PROMPT


@pytest.mark.parametrize("extra", [None, "", "   "])
def test_an_empty_extra_does_not_change_the_prompt(extra: str | None) -> None:
    assert prompts.build_system_prompt(extra) == prompts.SYSTEM_PROMPT


def test_an_extra_instruction_is_appended_at_the_end() -> None:
    result = prompts.build_system_prompt("El usuario ya eligió un monitor.")

    assert result.startswith(prompts.SYSTEM_PROMPT)
    assert result.endswith("El usuario ya eligió un monitor.")
