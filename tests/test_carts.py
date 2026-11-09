"""Tests de backend/carts.py: el almacén de carritos en memoria."""

from __future__ import annotations

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
