// steps/core.mjs
import { execa } from 'execa'

/**
 * Create a generic step descriptor.
 * @param {object} config - Step configuration
 * @returns {object} Step descriptor
 */
export function makeStep({ id, kind, cmd, args = [], cwd, env, label, captureTo }) {
  return {
    id,
    kind,
    cmd,
    args,
    cwd,
    env,
    label: label || id,
    captureTo,
  }
}

/**
 * Execute a single step descriptor using the appropriate execution strategy.
 * @param {object} step - Step descriptor
 * @param {object} context - Execution context ({ logger, verbose })
 */
export async function executeStep(step, { logger = m => console.log(m), verbose = false } = {}) {
  const { cmd, args = [], cwd, captureTo, label, id } = step
  const tag = label || id || cmd

  if (verbose) logger(`Starting step ${tag}: ${cmd} ${args.join(' ')}`)

  if (captureTo) {
    return runAndCapture(cmd, args, { cwd, teeToFile: captureTo })
  } else {
    return runWithProgress(cmd, args, {
      logger: verbose ? logger : () => {},
      label: tag,
      opts: { cwd },
      showExec: false,
    })
  }
}

/**
 * Execute an array of steps sequentially.
 * @param {Array} steps - Array of step descriptors
 * @param {object} context - Execution context ({ logger, verbose })
 * @param {object} opts - Additional options ({ sleepBetween: seconds })
 */
export async function executeSteps(steps, context = {}, opts = {}) {
  const { sleepBetween = 0 } = opts
  const { logger = m => console.log(m), verbose = false } = context
  
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i]
    await executeStep(step, { logger, verbose })
    
    // Sleep between steps if requested (but not after the last one)
    if (sleepBetween > 0 && i < steps.length - 1) {
      if (verbose) logger(`Waiting ${sleepBetween}s before next step...`)
      await new Promise(resolve => setTimeout(resolve, sleepBetween * 1000))
    }
  }
}

/**
 * Run a command with inherited stdio.
 * @param {string} cmd - Command executable
 * @param {string[]} args - Command arguments
 * @param {object} opts - Additional execa options
 */
export function run(cmd, args = [], opts = {}) {
  return execa(cmd, args, {
    stdout: 'inherit',
    stderr: 'inherit',
    stdin: 'inherit',
    ...opts
  })
}

/**
 * Run a command, capture stdout, and optionally tee to a file.
 * @param {string} cmd - Command executable
 * @param {string[]} args - Command arguments
 * @param {object} opts - Options including teeToFile
 * @returns {Promise<{stdout: string, stderr: string}>}
 */
export async function runAndCapture(cmd, args = [], opts = {}) {
  const { teeToFile, ...spawnOpts } = opts
  const child = execa(cmd, args, {
    stdin: 'inherit',
    stdout: 'pipe',
    stderr: 'pipe',
    ...spawnOpts
  })
  let out = ''
  let err = ''
  let writeStream = null
  if (teeToFile) {
    writeStream = (await import('fs')).createWriteStream(teeToFile, { encoding: 'utf8' })
  }
  if (child.stdout) {
    child.stdout.on('data', chunk => {
      const s = chunk.toString()
      out += s
      process.stdout.write(s)
      if (writeStream) writeStream.write(s)
    })
  }
  if (child.stderr) {
    child.stderr.on('data', chunk => {
      const s = chunk.toString()
      err += s
      process.stderr.write(s)
    })
  }
  await child
  if (writeStream) writeStream.end()
  return { stdout: out, stderr: err }
}

/**
 * Run a command with progress heartbeat logging.
 * @param {string} cmd - Command executable
 * @param {string[]} args - Command arguments
 * @param {object} config - Configuration ({ logger, label, intervalMs, opts, showExec })
 */
export async function runWithProgress(cmd, args = [], { logger = m => console.log(m), label, intervalMs = 5000, opts = {}, showExec = true } = {}) {
  const started = Date.now()
  if (showExec) {
    logger(`→ exec: ${cmd} ${args.join(' ')}`)
  }
  const child = execa(cmd, args, {
    stdout: 'inherit',
    stderr: 'inherit',
    stdin: 'inherit',
    ...opts
  })
  const tag = label || cmd
  const timer = setInterval(() => {
    logger(`${tag} running ${(Date.now() - started) / 1000}s`)
  }, intervalMs)
  try {
    await child
    logger(`${tag} finished in ${(Date.now() - started) / 1000}s`)
  } finally {
    clearInterval(timer)
  }
}
