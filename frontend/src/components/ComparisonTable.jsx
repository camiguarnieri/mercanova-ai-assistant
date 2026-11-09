/**
 * Tabla de una comparación de productos.
 *
 * Se arma con el resultado de compare_products, no con el texto del asistente:
 * el modelo ya escribió un valor al revés al pasarlo a prosa. Mismo criterio
 * que la traza de herramientas: lo que se muestra como dato sale del catálogo,
 * y el texto del modelo queda al lado como explicación.
 *
 * Cada celda viene ya escrita del backend (backend/catalog_text.py), con su
 * unidad: "0 h", "40 h", "5.3". Es el mismo texto que recibió el modelo, así
 * la tabla y lo que él leyó no pueden decir cosas distintas. Cada valor trae
 * también el nombre del producto, que acá no se usa —la columna ya lo dice— y
 * está para que el modelo no tenga que traducir el product_id al escribir.
 */

import { MISSING } from '../format.js'

export default function ComparisonTable({ comparison }) {
  const { products, specifications } = comparison
  if (!products || products.length === 0) {
    return null
  }

  return (
    <figure className="comparison">
      <figcaption>Comparación del catálogo</figcaption>
      <table>
        <thead>
          <tr>
            <th scope="col">Característica</th>
            {products.map((product) => (
              <th key={product.product_id} scope="col">
                {product.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {specifications.map((specification) => (
            <tr key={`${specification.attribute_group}-${specification.attribute_name}`}>
              <th scope="row">
                {specification.attribute_name}
                <span className="comparison-group">{specification.attribute_group}</span>
              </th>
              {products.map((product) => (
                <td key={product.product_id}>
                  {specification.values[product.product_id]?.value || MISSING}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {specifications.length === 0 ? (
        <p className="comparison-empty">
          Estos productos no tienen ninguna especificación en común en el catálogo.
        </p>
      ) : null}
    </figure>
  )
}
