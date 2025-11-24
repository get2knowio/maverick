// steps/coderabbit.mjs
import { makeStep } from './core.mjs'

/**
 * Create a coderabbit command step descriptor.
 * @param {string} id - Unique step identifier
 * @param {string[]} args - Command arguments
 * @param {object} opts - Additional options (cwd, label, captureTo)
 */
export function makeCoderabbitStep(id, args = [], opts = {}) {
  return makeStep({
    id,
    kind: 'coderabbit',
    cmd: 'coderabbit',
    args,
    cwd: opts.cwd,
    label: opts.label,
    captureTo: opts.captureTo,
  })
}

/**
 * Convenience helper to create a coderabbit step with minimal syntax.
 * @param {string} id - Step identifier
 * @param {string[]} args - Command arguments
 * @param {object} opts - Additional options
 */
export function coderabbitStep(id, args = [], opts = {}) {
  return makeCoderabbitStep(id, args, opts)
}
