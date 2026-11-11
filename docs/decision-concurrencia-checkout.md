# Concurrencia del checkout: dos compras del mismo carrito

Decisión del tramo de robustez, para poder defenderla sin leer el código.

## Problema

Dos pedidos `POST /checkout` simultáneos de la misma sesión creaban **dos
órdenes** y descontaban el stock **dos veces**.

La secuencia de `orders.checkout()` es: leer el carrito, validarlo contra el
catálogo, escribir la orden, vaciar el carrito. Solo el tercer paso estaba
protegido, por la transacción de SQLite. Los otros tres no, y ahí está el bug:

1. Los dos pedidos leen el carrito, que vive en la memoria del proceso.
2. Los dos validan stock contra la base y los dos pasan.
3. El primero toma el write lock de SQLite y escribe su orden. El segundo
   recibe `SQLITE_BUSY`, reintenta durante los 5 segundos del `timeout` por
   default de `sqlite3.connect`, consigue el lock y **escribe la suya**.
4. `store.clear()` corre dos veces; la segunda no tiene nada que borrar.

La transacción de SQLite no podía evitarlo: **el carrito no está en la base**.
Serializar las escrituras no alcanza cuando la decisión de escribir se tomó
leyendo un estado que la base no ve.

Lo que sí estaba protegido era el stock contra números negativos:
`inventory.reduce_stock()` lee `available_qty` fresco adentro de su propia
transacción, así que si no alcanza levanta `StockWriteError` y la transacción se
deshace entera. Con stock 10 y pedido de 2 se cobraban dos órdenes; con stock 2
la segunda fallaba con un 409 correcto. El daño era la orden duplicada, no un
stock inconsistente.

Reproducido en `tests/test_cart_api.py::test_two_simultaneous_checkouts_create_exactly_one_order`:
sin el arreglo, los dos pedidos contestan 201.

## Alternativas consideradas

**1. Resolverlo en la base de datos.** Mover el carrito a una tabla con un
estado (`open` / `ordered`) y confirmar con un
`UPDATE carts SET status='ordered' WHERE session_id=? AND status='open'`,
mirando cuántas filas tocó: la segunda toca cero y no crea nada. Es la solución
que sobrevive a varios procesos, porque el árbitro pasa a ser la base.

Descartada en este tramo porque **obliga a mover el carrito a SQLite**, que es
una decisión ya tomada y documentada en `decision-carrito-y-checkout.md` por
otros motivos (el carrito guarda solo cantidades y los precios se releen del
catálogo). Es un cambio de alcance mucho mayor que el bug que arregla.

Una variante más chica —una `UNIQUE` que impida dos órdenes iguales— no sirve:
no hay clave natural para "una orden por carrito", y la misma persona puede
comprar dos veces lo mismo legítimamente, más tarde.

**2. Clave de idempotencia.** El cliente manda una clave por intento de compra;
el servidor la guarda con una `UNIQUE` y, si la clave repite, devuelve la orden
que ya había creado en vez de crear otra. Es la respuesta estándar de la
industria de pagos.

Descartada **como arreglo de este bug**, por dos razones. La primera es que
resuelve un problema distinto y mejor: el doble clic y el reintento de red, que
son dos pedidos *separados en el tiempo*. Para dos pedidos *simultáneos* sobre
el mismo carrito, dos claves distintas pasarían las dos. La segunda es el costo:
cambia el contrato (`CheckoutRequest` gana un campo obligatorio), obliga al
frontend a generar y persistir la clave, y suma una tabla. No lo descartamos por
malo: es lo que agregaríamos si el carrito se fuera a la base o si quisiéramos
cubrir el reintento. Es complementario, no sustituto.

**3. Deshabilitar el botón en el frontend.** No es un arreglo del servidor:
cualquier cliente —un `curl`, una pestaña duplicada— sigue pudiendo hacerlo. Es
buena UX y no reemplaza nada.

**4. Verificar de nuevo adentro de la transacción.** No funciona: el carrito
está en memoria, así que la transacción no lo ve y una relectura dentro de ella
devuelve lo mismo que la de afuera.

**5. Un lock global del checkout.** Correcto y de una línea, pero convierte
todas las compras en una fila única: la compra de una persona espera a la de
otra sin ninguna razón.

## Decisión

Un **lock por sesión**, en `CartStore.session_lock()`, que envuelve la secuencia
completa de `orders.checkout()`: leer, validar, escribir y vaciar.

```python
with store.session_lock(session_id):
    lines = checked_lines(connection, cart.view(connection, store, session_id))
    ...
    with connection:        # la transacción, adentro del lock
        ...
    store.clear(session_id)
```

El segundo pedido espera a que el primero termine, y cuando entra se encuentra
el carrito **ya vacío**: `checked_lines()` levanta `EmptyCartError` y el handler
de `api.py` lo traduce a un **409** con el mensaje "El carrito está vacío:
agregá al menos un producto antes de confirmar la compra."

## Justificación

**El lock vive donde vive el carrito.** El carrito está en la memoria de este
proceso: si mañana se levantan dos workers, cada uno tiene los suyos y el
segundo worker no vería el carrito de la sesión ni con un lock distribuido. Un
lock en memoria es exactamente tan durable como la cosa que protege, y eso es lo
que hace que alcance acá y que no alcance si el carrito se fuera a la base. La
alternativa 1 es la correcta en ese escenario, y el día que ese escenario
aparezca, el arreglo correcto cambia con él.

**Es por sesión y no global.** Dos sesiones toman locks distintos, así que una
compra no hace fila detrás de la de otra persona. Está fijado con un test que
toma el lock de una sesión y confirma que el checkout de otra igual contesta
201: si el lock fuera global, ese test se colgaría.

**Se libera siempre**, incluso si el checkout falla a mitad de camino: es un
`with` sobre un `Lock`, no un par de llamadas a mano.

**No hay deadlock con SQLite.** Adentro del bloque se toma primero el lock de la
sesión y después el de la base, nunca al revés: ninguna ruta abre una
transacción y después pide un lock de sesión. Y un hilo tiene como máximo un
lock de sesión, nunca dos, así que no puede haber espera circular. El orden es
siempre `lock de sesión → lock de SQLite`.

El `_lock` que protege los diccionarios de `CartStore` se toma solo para buscar
o crear el lock de la sesión, y **se suelta antes de esperarlo**. Si se
mantuviera, un checkout en curso bloquearía a todas las demás sesiones y esto
sería la alternativa 5 con pasos de más.

**Es explicable en la defensa en un minuto**, que para este trabajo cuenta.

## Trade-offs

| Costo | Detalle |
|---|---|
| No sirve con varios workers | Un lock en memoria no cruza procesos. Para ese escenario hay que ir a la alternativa 1, y además el carrito ya no funcionaría sin eso: la limitación es del carrito en memoria, no del lock. |
| El mensaje del 409 es cierto pero no el más preciso | El segundo pedido recibe "el carrito está vacío", que es literalmente lo que pasó. Para alguien que hizo doble clic, "esta compra ya se confirmó" sería más claro. No lo agregamos para no inventar estado nuevo; con la clave de idempotencia (alternativa 2) saldría gratis y además devolvería la orden ya creada. |
| Un `Lock` por sesión que no se libera | `_session_locks` crece con cada sesión que hace checkout y no se limpia: sacar el lock del diccionario mientras alguien lo espera es peor. Es un objeto chico por sesión, del mismo orden que las conversaciones que `SessionStore` ya guarda para siempre. |
| El segundo pedido espera | La espera es la duración del primer checkout. Es corta y acotada: el checkout no hace red ni llama al modelo, solo SQLite local. Si esa sección creciera, el knob es `acquire(timeout=...)` para cortar en vez de esperar. |

## Lo que quedó sin arreglar, a propósito

`cart.add_item()` tiene el mismo patrón —`check_stock()` y después
`set_quantity()`, sin atomicidad— y **no se tocó**. Dos `add_item` simultáneos
del mismo producto pueden dejar en el carrito más unidades que el stock.

No es un bug equivalente: agregar al carrito es reversible y **no escribe nada
en la base**. Lo único que puede quedar mal es una cantidad en memoria, y el
checkout la vuelve a validar contra el catálogo antes de escribir
(`orders.checked_lines()` llama a `cart.check_stock()` de nuevo). El peor caso
es que el usuario vea un carrito con 7 unidades de algo que tiene 5 y reciba un
409 al confirmar, con el mensaje que dice cuántas hay.

Arreglarlo es envolver `add_item` y `set_quantity` en el mismo
`session_lock()`. Queda anotado como riesgo aceptado y no como olvido.
