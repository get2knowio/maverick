// steps/shell.mjs
import { makeStep } from './core.mjs'

/**
 * Create a shell command step descriptor.
 * @param {string} id - Unique step identifier
 * @param {string} cmd - Command executable
 * @param {string[]} args - Command arguments
 * @param {object} opts - Additional options (cwd, env, label, captureTo)
 */
export function makeShellStep(id, cmd, args = [], opts = {}) {
  return makeStep({
    id,
    kind: 'shell',
    cmd,
    args,
    cwd: opts.cwd,
    env: opts.env,
    label: opts.label,
    captureTo: opts.captureTo,
  })
}

/**
 * Convenience helper to create a shell step with minimal syntax.
 * @param {string} id - Step identifier
 * @param {string} cmd - Command to run
 * @param {string[]} args - Command arguments
 * @param {object} opts - Additional options
 */
export function shellStep(id, cmd, args = [], opts = {}) {
  return makeShellStep(id, cmd, args, opts)
}
