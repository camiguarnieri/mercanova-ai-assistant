/** Especificaciones técnicas, agrupadas por attribute_group. */

import { formatSpecification, groupSpecifications } from '../format.js'
import { Empty } from './Notice.jsx'

// Muestra una tabla por grupo. El valor sale de formatSpecification, que
// respeta el 'None' del catálogo: significa que el producto no lo tiene.
export default function SpecificationGroups({ specifications }) {
  if (specifications.length === 0) {
    return <Empty title="Sin especificaciones">El catálogo no tiene especificaciones cargadas para este producto.</Empty>
  }

  return (
    <div className="specs">
      {groupSpecifications(specifications).map(({ group, items }) => (
        <section key={group} className="specs-group">
          <h3>{group}</h3>
          <table>
            <tbody>
              {items.map((specification) => (
                <tr key={`${group}-${specification.attribute_name}`}>
                  <th scope="row">{specification.attribute_name}</th>
                  <td>{formatSpecification(specification)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  )
}
