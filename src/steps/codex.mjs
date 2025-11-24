// steps/codex.mjs
import { makeStep } from './core.mjs'

/**
 * Create a codex command step descriptor.
 * @param {string} id - Unique step identifier
 * @param {string} prompt - The prompt to pass to codex
 * @param {object} opts - Additional options (model, cwd, label, captureTo, dangerouslyBypassApprovalsAndSandbox)
 */
export function makeCodexStep(id, prompt, opts = {}) {
  const args = [
    'exec',
  ]
  
  if (opts.dangerouslyBypassApprovalsAndSandbox) {
    args.push('--dangerously-bypass-approvals-and-sandbox')
  }
  
  if (opts.model) {
    args.push('-m', opts.model)
  }
  
  args.push(prompt)

  return makeStep({
    id,
    kind: 'codex',
    cmd: 'codex',
    args,
    cwd: opts.cwd,
    label: opts.label,
    captureTo: opts.captureTo,
  })
}

/**
 * Convenience helper to create a codex step with minimal syntax.
 * @param {string} id - Step identifier
 * @param {string} prompt - Prompt for codex
 * @param {object} opts - Additional options
 */
export function codexStep(id, prompt, opts = {}) {
  return makeCodexStep(id, prompt, opts)
}
