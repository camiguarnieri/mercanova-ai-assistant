"""Tests de backend/carts.py: el almacén de carritos en memoria."""

from __future__ import annotations

from threading import Event, Thread

import pytest

from backend.carts import CartSession, CartStore


def test_a_new_session_has_an_empty_cart() -> None:
    store = CartStore()

    assert store.items("s-1") == {}
    assert store.quantity("s-1", "MN-MON-0001") == 0


def test_the_quantity_of_a_product_is_the_one_that_was_set() -> None:
    store = CartStore()

    store.set_quantity("s-1", "MN-MON-0001", 3)

    assert store.items("s-1") == {"MN-MON-0001": 3}
    assert store.quantity("s-1", "MN-MON-0001") == 3


def test_setting_zero_removes_the_line() -> None:
    store = CartStore()
    store.set_quantity("s-1", "MN-MON-0001", 2)

    store.set_quantity("s-1", "MN-MON-0001", 0)

    # Un carrito no guarda líneas en cero: la línea se va.
    assert store.items("s-1") == {}


def test_the_items_keep_the_order_in_which_they_were_added() -> None:
    store = CartStore()

    store.set_quantity("s-1", "MN-MON-0001", 1)
    store.set_quantity("s-1", "MN-HDP-0001", 2)
    store.set_quantity("s-1", "MN-MON-0001", 5)

    assert list(store.items("s-1")) == ["MN-MON-0001", "MN-HDP-0001"]


def test_removing_says_whether_the_product_was_there() -> None:
    store = CartStore()
    store.set_quantity("s-1", "MN-MON-0001", 1)

    assert store.remove("s-1", "MN-MON-0001") is True
    assert store.remove("s-1", "MN-MON-0001") is False


def test_each_session_has_its_own_cart() -> None:
    store = CartStore()

    store.set_quantity("s-1", "MN-MON-0001", 1)
    store.set_quantity("s-2", "MN-HDP-0001", 4)

    assert store.items("s-1") == {"MN-MON-0001": 1}
    assert store.items("s-2") == {"MN-HDP-0001": 4}
    assert store.count() == 2


def test_clearing_empties_the_cart_of_one_session() -> None:
    store = CartStore()
    store.set_quantity("s-1", "MN-MON-0001", 1)
    store.set_quantity("s-2", "MN-HDP-0001", 1)

    store.clear("s-1")

    assert store.items("s-1") == {}
    assert store.items("s-2") == {"MN-HDP-0001": 1}


def test_the_items_are_a_copy_of_what_is_stored() -> None:
    store = CartStore()
    store.set_quantity("s-1", "MN-MON-0001", 1)

    store.items("s-1")["MN-MON-0001"] = 99

    assert store.quantity("s-1", "MN-MON-0001") == 1


def test_a_cart_session_ties_a_store_to_one_session() -> None:
    store = CartStore()

    session = CartSession(store, "s-1")

    assert session.store is store
    assert session.session_id == "s-1"


def test_the_session_lock_lets_the_cart_be_used_inside_it() -> None:
    # Adentro del lock se siguen llamando los métodos del almacén, que toman su
    # propio lock: si fueran el mismo, esto se colgaría.
    store = CartStore()

    with store.session_lock("s-1"):
        store.set_quantity("s-1", "MN-MON-0001", 2)
        quantity = store.quantity("s-1", "MN-MON-0001")
        store.clear("s-1")

    assert quantity == 2
    assert store.items("s-1") == {}


def test_the_session_lock_serializes_the_same_session() -> None:
    store = CartStore()
    holding = Event()
    release = Event()
    got_in = Event()

    def hold() -> None:
        with store.session_lock("s-1"):
            holding.set()
            release.wait(timeout=5)

    def contend() -> None:
        with store.session_lock("s-1"):
            got_in.set()

    holder = Thread(target=hold)
    holder.start()
    assert holding.wait(timeout=5)

    second = Thread(target=contend)
    second.start()
    # Mientras el primero lo tiene, el segundo no entra.
    assert not got_in.wait(timeout=0.3)

    release.set()
    # Y en cuanto el primero sale, entra.
    assert got_in.wait(timeout=5)
    holder.join(timeout=5)
    second.join(timeout=5)


def test_the_session_lock_does_not_serialize_other_sessions() -> None:
    # Lo que hace que una compra no haga fila detrás de la de otra persona.
    store = CartStore()
    holding = Event()
    release = Event()
    got_in = Event()

    def hold() -> None:
        with store.session_lock("s-1"):
            holding.set()
            release.wait(timeout=5)

    def other_session() -> None:
        with store.session_lock("s-2"):
            got_in.set()

    holder = Thread(target=hold)
    holder.start()
    assert holding.wait(timeout=5)

    Thread(target=other_session).start()

    # Con el lock de 's-1' tomado, 's-2' no espera: toma el suyo y sigue.
    assert got_in.wait(timeout=5)
    release.set()
    holder.join(timeout=5)


def test_the_session_lock_is_released_when_the_block_fails() -> None:
    store = CartStore()

    with pytest.raises(ValueError):
        with store.session_lock("s-1"):
            raise ValueError("algo falló a mitad de camino")

    # Si no se hubiera liberado, este bloque no entraría nunca.
    taken = Event()

    def take() -> None:
        with store.session_lock("s-1"):
            taken.set()

    Thread(target=take, daemon=True).start()

    assert taken.wait(timeout=5)
