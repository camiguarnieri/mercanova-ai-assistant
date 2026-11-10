# Carrito y checkout: qué hace el modelo y qué hace el usuario

Decisión del tramo 3, para poder defenderla sin leer el código.

## La regla

El modelo **agrega y quita** productos del carrito. El modelo **no confirma
compras**. La orden la crea el usuario desde la interfaz, con una confirmación
explícita del resumen.

El criterio es la reversibilidad. Agregar algo de más al carrito se arregla
sacándolo, y el usuario lo ve en pantalla mientras conversa. Confirmar una
compra descuenta stock de la base y crea una orden con identificador: no se
deshace, así que no la decide el modelo.

## Cómo está garantizado, no solo pedido

No alcanza con decirlo en el prompt. Está sostenido en código:

| Garantía | Dónde |
|---|---|
| El modelo tiene herramientas para agregar y quitar, y ninguna para comprar | `tool_schemas.py`: `CART_TOOL_NAMES` son `add_to_cart` y `remove_from_cart`; `orders.py` no está en `IMPLEMENTATIONS` |
| El checkout exige confirmación explícita | `cart_models.CheckoutRequest.confirmed` es `Literal[True]`: sin eso el pedido no valida y no se crea nada (RF-12) |
| El modelo solo toca el carrito de su conversación | `assistant.py` arma el `CartSession` con el `session_id` del pedido; no es un argumento de la herramienta |
| El modelo no puede inventar un producto para agregar | `provenance.check_ids()` corre antes de ejecutar, igual que con las herramientas del catálogo |
| El stock se valida contra la base | `cart.check_stock()` lee `available_qty` del catálogo al agregar, y `orders.checked_lines()` lo vuelve a leer al confirmar |
| El modelo no afirma un total que calculó él | `cart_tools.cart_message()` le entrega el total ya escrito, calculado por el sistema con los precios del catálogo |
| El modelo no repite cantidades de stock viejas | `cart_tools.cart_for_the_model()` saca `available_qty` de lo que lee el modelo: la cantidad sigue saliendo solo de `check_availability` |

## Dónde vive cada cosa

- **El carrito, en memoria** (`carts.py`), por `session_id`, igual que las
  conversaciones. Se pierde al reiniciar la API, y está asumido.
- **La orden, en la base** (`orders`, `order_items`). Tiene que estar ahí
  porque confirmar también descuenta stock de `inventory`: las dos escrituras
  van en la misma transacción, así no queda stock descontado sin orden ni orden
  sin stock descontado (RF-15).
- **Las dos tablas son datos operativos del equipo**, no salen del Excel de la
  cátedra. Por eso no están en `db.TABLES`, que es lo que la carga del dataset
  vacía y vuelve a escribir.

El carrito guarda solo `{product_id: cantidad}`. El nombre, el precio y el
stock se leen del catálogo cada vez que se muestra: un carrito que guardara el
precio mostraría un número viejo. La orden sí los copia, a propósito: es la
foto de lo que el usuario confirmó (RF-14).

## La regla del carrito no está en el prompt del sistema

Está en la descripción de `add_to_cart` y `remove_from_cart`, que viaja al
modelo en cada pedido igual que el prompt.

El motivo es el presupuesto que verifica `tests/test_prompts.py`: el prompt
está en 880 tokens de los 900 que se fijaron después de medir el techo de
instrucciones del modelo, y la regla es que cada regla nueva saca otra. Las que
podría haber sacado son las tres que ese archivo justifica con una falla
observada en una corrida real, así que la del carrito se puso donde no compite
con ellas. Si el equipo prefiere un bloque `CARRITO` en el prompt, hay que
decidir cuál sale.
