"""Tests de backend/sessions.py: las conversaciones guardadas en memoria."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.sessions import SessionStore

SALUDO = [{"role": "user", "content": "Hola"}]


def test_a_new_session_has_no_conversation() -> None:
    # None distingue "sesión nueva" de "sesión sin mensajes": con una nueva hay
    # que armar el prompt del sistema.
    assert SessionStore().history("s-1") is None


def test_what_was_saved_comes_back() -> None:
    store = SessionStore()

    store.save("s-1", SALUDO)

    assert store.history("s-1") == SALUDO


def test_saving_again_replaces_the_conversation() -> None:
    store = SessionStore()
    store.save("s-1", SALUDO)

    store.save("s-1", [*SALUDO, {"role": "assistant", "content": "Hola, ¿qué buscás?"}])

    assert len(store.history("s-1")) == 2


def test_each_session_has_its_own_conversation() -> None:
    store = SessionStore()

    store.save("s-1", SALUDO)
    store.save("s-2", [{"role": "user", "content": "Quiero un monitor"}])

    assert store.history("s-1") == SALUDO


def test_one_session_does_not_see_another_one() -> None:
    store = SessionStore()

    store.save("s-1", SALUDO)

    assert store.history("s-2") is None


def test_the_conversation_that_is_returned_is_a_copy() -> None:
    store = SessionStore()
    store.save("s-1", SALUDO)

    store.history("s-1").append({"role": "user", "content": "Colado"})

    assert len(store.history("s-1")) == 1


def test_the_saved_list_is_not_the_one_that_was_received() -> None:
    store = SessionStore()
    messages = list(SALUDO)
    store.save("s-1", messages)

    messages.append({"role": "user", "content": "Colado"})

    assert len(store.history("s-1")) == 1


def test_a_new_session_knows_no_products() -> None:
    assert SessionStore().known_products("s-1") == set()


def test_the_products_that_were_seen_come_back() -> None:
    store = SessionStore()

    store.remember_products("s-1", {"MN-MON-0001"})

    assert store.known_products("s-1") == {"MN-MON-0001"}


def test_the_products_of_a_turn_are_added_to_the_previous_ones() -> None:
    # Lo que el modelo vio una vez lo puede seguir usando en el mismo chat.
    store = SessionStore()
    store.remember_products("s-1", {"MN-MON-0001"})

    store.remember_products("s-1", {"MN-HDP-0001"})

    assert store.known_products("s-1") == {"MN-MON-0001", "MN-HDP-0001"}


def test_one_session_does_not_see_the_products_of_another() -> None:
    store = SessionStore()

    store.remember_products("s-1", {"MN-MON-0001"})

    assert store.known_products("s-2") == set()


def test_the_products_that_are_returned_are_a_copy() -> None:
    store = SessionStore()
    store.remember_products("s-1", {"MN-MON-0001"})

    store.known_products("s-1").add("MN-COLADO-0001")

    assert store.known_products("s-1") == {"MN-MON-0001"}


def test_an_empty_store_has_no_sessions() -> None:
    assert SessionStore().count() == 0


def test_the_sessions_are_counted() -> None:
    store = SessionStore()

    store.save("s-1", SALUDO)
    store.save("s-2", SALUDO)

    assert store.count() == 2


def test_several_threads_can_save_at_the_same_time() -> None:
    # Como los pedidos del threadpool de FastAPI: sin el lock esto se corrompe.
    store = SessionStore()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: store.save(f"s-{index}", SALUDO), range(50)))

    assert store.count() == 50

