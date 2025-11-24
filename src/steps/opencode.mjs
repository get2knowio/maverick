// steps/opencode.mjs
import { makeStep } from './core.mjs'

/**
 * Create an opencode command step descriptor.
 * @param {string} id - Unique step identifier
 * @param {string} prompt - The prompt to pass to opencode
 * @param {object} opts - Additional options (model, cwd, command, label, captureTo)
 */
export function makeOpencodeStep(id, prompt, opts = {}) {
  const args = [
    'run',
    '--model',
    opts.model || 'github-copilot/claude-sonnet-4.5',
  ]
  if (opts.command) {
    args.push('--command', opts.command)
  }
  args.push(prompt)

  return makeStep({
    id,
    kind: 'opencode',
    cmd: 'opencode',
    args,
    cwd: opts.cwd,
    label: opts.label,
    captureTo: opts.captureTo,
  })
}

/**
 * Convenience helper to create an opencode step with minimal syntax.
 * @param {string} id - Step identifier
 * @param {string} prompt - Prompt for opencode
 * @param {object} opts - Additional options
 */
export function opencodeStep(id, prompt, opts = {}) {
  return makeOpencodeStep(id, prompt, opts)
}
