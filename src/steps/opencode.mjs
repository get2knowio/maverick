// steps/opencode.mjs
import { makeStep } from './core.mjs'
import { fileURLToPath } from 'url'
import path from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Path to Maverick's bundled OpenCode config with full permissions
const MAVERICK_OPENCODE_CONFIG = path.join(__dirname, '..', '..', 'config', 'opencode-maverick.json')

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

  // Set OPENCODE_CONFIG to use Maverick's bundled config with full permissions
  // This will be merged with any existing project config without overriding model settings
  const env = {
    ...process.env,
    OPENCODE_CONFIG: MAVERICK_OPENCODE_CONFIG,
  }

  return makeStep({
    id,
    kind: 'opencode',
    cmd: 'opencode',
    args,
    cwd: opts.cwd,
    env,
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
