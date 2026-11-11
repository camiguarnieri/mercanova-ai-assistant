/** Preparación común de los tests: matchers del DOM y desmontaje entre casos. */

import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom no implementa scrollIntoView, que el chat usa para seguir la
// conversación. No hay nada que probar ahí: alcanza con que exista.
Element.prototype.scrollIntoView = () => {}

afterEach(() => {
  cleanup()
})
