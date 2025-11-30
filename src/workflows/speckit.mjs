// workflows/default.mjs
import fs from 'fs/promises'
import os from 'os'
import path from 'path'
import { execa } from 'execa'
import { parsePhases } from '../tasks/markdown.mjs'
import { executeStep, run, runAndCapture } from '../steps/core.mjs'
import { makeOpencodeStep } from '../steps/opencode.mjs'
import {
  opencodeImplementPhase,
  codexReview,
  codexCoderabbitReview,
  codexOrganizeFixes,
  opencodeFix,
} from '../steps/speckit.mjs'

// Default sleep between phases in seconds
export const PHASE_SLEEP_SECONDS = 5

/**
 * Parse `git worktree list --porcelain` output to find an existing worktree for a branch.
 */
async function findExistingWorktree(repoRoot, branch) {
  try {
    const { stdout } = await runAndCapture('git', ['worktree', 'list', '--porcelain'], { cwd: repoRoot })
    const blocks = stdout.split('\n\n').map(block => block.trim()).filter(Boolean)
    for (const block of blocks) {
      const lines = block.split('\n')
      const worktreeLine = lines.find(l => l.startsWith('worktree '))
      const branchLine = lines.find(l => l.startsWith('branch '))
      if (!worktreeLine || !branchLine) continue
      const worktreePath = worktreeLine.replace('worktree ', '').trim()
      const branchRef = branchLine.replace('branch ', '').trim()
      if (branchRef === `refs/heads/${branch}`) {
        return { path: worktreePath, branch: branchRef }
      }
    }
  } catch {
    // Ignore errors and behave as if no existing worktree is present.
  }
  return null
}

/**
 * Check whether a ref exists in the repo.
 */
async function refExists(repoRoot, ref) {
  try {
    await run('git', ['show-ref', '--verify', '--quiet', ref], { cwd: repoRoot })
    return true
  } catch {
    return false
  }
}

/**
 * Prepare a temporary worktree rooted outside the current working directory.
 */
export async function prepareWorktree({
  repoRoot,
  branch,
  logger = m => console.log(m),
  verbose = false,
  reuseExistingWorktree = false,
  cleanExistingWorktree = false
}) {
  const existing = await findExistingWorktree(repoRoot, branch)

  if (existing) {
    if (reuseExistingWorktree) {
      if (verbose) logger(`Reusing existing worktree for ${branch} at ${existing.path}`)
      return { worktreePath: existing.path, cleanup: async () => {} }
    } else {
      // Default behavior: clean the existing worktree and create a fresh one
      if (verbose) logger(`Removing existing worktree for ${branch} at ${existing.path}...`)
      await run('git', ['worktree', 'remove', '-f', existing.path], { cwd: repoRoot })
    }
  }

  const worktreeBase = await fs.mkdtemp(path.join(os.tmpdir(), 'maverick-worktree-'))
  const worktreePath = path.join(worktreeBase, branch.replace(/[\\/]/g, '_') || 'branch')

  const remoteBranch = `origin/${branch}`
  let baseRef = 'main'

  // Prefer the remote branch if it exists, otherwise fall back to local branch, then main.
  try {
    await run('git', ['fetch', 'origin', branch], { cwd: repoRoot })
    if (await refExists(repoRoot, `refs/remotes/${remoteBranch}`) || await refExists(repoRoot, remoteBranch)) {
      baseRef = remoteBranch
    }
  } catch (error) {
    if (verbose) logger(`Could not fetch ${remoteBranch}: ${error.message}`)
  }

  if (baseRef === 'main' && await refExists(repoRoot, `refs/heads/${branch}`)) {
    baseRef = branch
  }

  if (verbose) logger(`Using ${baseRef} as base ref for worktree`)

  if (verbose) logger(`Creating worktree for ${branch} at ${worktreePath}...`)
  await run('git', ['worktree', 'add', '-B', branch, worktreePath, baseRef], { cwd: repoRoot })

  const cleanup = async ({ deleteBranch = false } = {}) => {
    if (verbose) logger(`Removing worktree at ${worktreePath}...`)
    try {
      await run('git', ['worktree', 'remove', '-f', worktreePath], { cwd: repoRoot })
    } catch (error) {
      if (verbose) logger(`Worktree removal failed: ${error.message}`)
    }

    if (deleteBranch) {
      try {
        await run('git', ['branch', '-D', branch], { cwd: repoRoot })
      } catch (error) {
        if (verbose) logger(`Branch deletion failed: ${error.message}`)
      }
    }

    try {
      await fs.rm(worktreeBase, { recursive: true, force: true })
    } catch (error) {
      if (verbose) logger(`Failed to remove temp dir ${worktreeBase}: ${error.message}`)
    }
  }

  return { worktreePath, cleanup }
}

/**
 * Build phase execution steps from parsed phase objects.
 */
function buildPhaseSteps({ phasesToRun, projectRoot, buildModel, verbose, logger }) {
  return phasesToRun.map(phase => {
    if (verbose) {
      const counts = `(${phase.outstandingTasks}/${phase.totalTasks} outstanding)`
      logger(`Building step for phase ${phase.identifier} ${counts}: ${phase.title}`)
    }
    
    return opencodeImplementPhase(phase.identifier, {
      cwd: projectRoot,
      model: buildModel,
      outstandingTasks: phase.outstandingTasks,
      totalTasks: phase.totalTasks,
      phaseTitle: phase.title,
    })
  })
}

/**
 * Build review steps (4-step codex-based review process).
 */
function buildReviewSteps({ projectRoot }) {
  return [
    codexReview({
      cwd: projectRoot,
    }),
    codexCoderabbitReview({
      cwd: projectRoot,
    }),
    codexOrganizeFixes({
      cwd: projectRoot,
    }),
  ]
}

/**
 * Build fix step to address review findings.
 */
function buildFixStep({ projectRoot, fixModel }) {
  return opencodeFix({
    cwd: projectRoot,
    model: fixModel,
  })
}

/**
 * Pause for operator confirmation between major steps.
 */
async function pauseIfEnabled({ enabled, label, logger = m => console.log(m) }) {
  if (!enabled) return
  const prompt = label
    ? `Paused after ${label}. Press Enter to continue.`
    : 'Paused. Press Enter to continue.'
  logger(prompt)
  await new Promise(resolve => {
    const resume = () => {
      process.stdin.pause()
      resolve()
    }
    process.stdin.resume()
    process.stdin.once('data', resume)
  })
}

/**
 * Finalize work: ensure commit, push, create/merge PR, and rely on cleanup to prune branch/worktree.
 */
async function finalizeWorkflow({ projectRoot, branch, logger = m => console.log(m), verbose = false }) {
  const git = (args) => run('git', args, { cwd: projectRoot })

  if (verbose) logger('Finalizing: committing remaining changes...')
  await git(['add', '-A'])
  await git(['commit', '-m', 'Workflow: final sync', '--allow-empty'])

  if (verbose) logger(`Pushing branch ${branch}...`)
  await git(['push', '-u', 'origin', branch])

  if (verbose) logger('Creating pull request...')
  await run('gh', ['pr', 'create', '--fill', '--head', branch, '--base', 'main'], { cwd: projectRoot })

  if (verbose) logger('Merging pull request and deleting remote branch...')
  await run('gh', ['pr', 'merge', '--merge', '--delete-branch'], { cwd: projectRoot })
}

/**
 * Run the default workflow: parse tasks, execute phases, review, and fix.
 * @param {object} config - Workflow configuration
 */
export async function runDefaultWorkflow({
  branch,
  phases: initialPhases,
  tasksPath,
  buildModel = 'github-copilot/claude-sonnet-4.5',
  reviewModel = 'github-copilot/claude-sonnet-4.5',
  fixModel = 'github-copilot/claude-sonnet-4.5',
  verbose = false,
  logger = m => console.log(m),
  maxRetriesPerPhase = 3,
  worktreePath,
  cleanupWorktree,
  pauseMajorSteps = false
}) {

  const projectRoot = worktreePath || process.cwd()
  let cleanupPerformed = false

  if (verbose) logger(`Running workflow in ${projectRoot} on branch ${branch}`)

  // Parse initial phases
  let phases = initialPhases

  // Process each phase sequentially
  for (let phaseIndex = 0; phaseIndex < phases.length; phaseIndex++) {
    let retryCount = 0
    let phaseComplete = false

    while (!phaseComplete && retryCount < maxRetriesPerPhase) {
      retryCount += 1

      // Re-parse tasks.md to get current status
      const currentPhases = await parsePhases(tasksPath, projectRoot)
      const currentPhase = currentPhases[phaseIndex]

      if (!currentPhase || (currentPhase.outstandingTasks ?? 0) === 0) {
        if (verbose) logger(`Phase ${currentPhase?.identifier || phaseIndex + 1} completed!`)
        phaseComplete = true
        break
      }

      const attemptLabel = retryCount > 1 ? ` (attempt ${retryCount}/${maxRetriesPerPhase})` : ''
      const counts = `(${currentPhase.outstandingTasks}/${currentPhase.totalTasks} outstanding)`
      if (verbose) logger(`Running phase ${currentPhase.identifier}${attemptLabel} ${counts}: ${currentPhase.title}`)

      // Build and execute phase step
      const phaseStep = opencodeImplementPhase(currentPhase.identifier, {
        cwd: projectRoot,
        model: buildModel,
        outstandingTasks: currentPhase.outstandingTasks,
        totalTasks: currentPhase.totalTasks,
        phaseTitle: currentPhase.title,
      })

      try {
        await executeStep(phaseStep, { logger, verbose })
      } catch (error) {
        logger(`ERROR: Phase ${currentPhase.identifier} execution failed: ${error.message}`)
        if (verbose && error.stack) {
          logger(`Stack trace: ${error.stack}`)
        }
        
        // If we've exhausted retries, fail the entire workflow
        if (retryCount >= maxRetriesPerPhase) {
          throw new Error(
            `Phase ${currentPhase.identifier} failed after ${maxRetriesPerPhase} attempts. ` +
            `Last error: ${error.message}`
          )
        }
        
        // Otherwise, log and retry
        logger(`Retrying phase ${currentPhase.identifier} (attempt ${retryCount + 1}/${maxRetriesPerPhase})...`)
        continue
      }

      // Commit the work for this phase attempt
      try {
        if (verbose) logger(`Committing work for phase ${currentPhase.identifier}...`)
        await run('git', ['add', '-A'], { cwd: projectRoot })
        const commitMsg = `Phase ${currentPhase.identifier}: ${currentPhase.title}${attemptLabel}`
        await run('git', ['commit', '-m', commitMsg, '--allow-empty'], { cwd: projectRoot })
        if (verbose) logger(`Committed: ${commitMsg}`)
      } catch (error) {
        if (verbose) logger(`Git commit failed (may be nothing to commit): ${error.message}`)
      }

      // Sleep before checking status or retrying
      if (verbose) logger(`Waiting ${PHASE_SLEEP_SECONDS}s before continuing...`)
      await new Promise(resolve => setTimeout(resolve, PHASE_SLEEP_SECONDS * 1000))

      // Re-check if phase is now complete
      const updatedPhases = await parsePhases(tasksPath, projectRoot)
      const updatedPhase = updatedPhases[phaseIndex]
      
      if (!updatedPhase || (updatedPhase.outstandingTasks ?? 0) === 0) {
        if (verbose) logger(`Phase ${currentPhase.identifier} completed after ${retryCount} attempt(s)!`)
        phaseComplete = true
      } else if (retryCount >= maxRetriesPerPhase) {
        // Phase still has outstanding tasks after max retries - fail the workflow
        throw new Error(
          `Phase ${currentPhase.identifier} incomplete after ${maxRetriesPerPhase} attempts. ` +
          `${updatedPhase.outstandingTasks}/${updatedPhase.totalTasks} tasks still outstanding.`
        )
      }
    }
  }

  await pauseIfEnabled({ enabled: pauseMajorSteps, label: 'phase loop', logger })

  // Build and execute review steps (3 codex steps)
  const reviewSteps = buildReviewSteps({ projectRoot })
  
  for (const step of reviewSteps) {
    await executeStep(step, { logger, verbose })
    
    // Sleep after each review step
    if (verbose) logger(`Waiting ${PHASE_SLEEP_SECONDS}s before next step...`)
    await new Promise(resolve => setTimeout(resolve, PHASE_SLEEP_SECONDS * 1000))
  }

  // Commit the organized fixes.md
  try {
    if (verbose) logger('Committing organized fixes.md...')
    await run('git', ['add', '-A'], { cwd: projectRoot })
    await run('git', ['commit', '-m', 'Review: organized fixes.md with parallelization markers', '--allow-empty'], { cwd: projectRoot })
    if (verbose) logger('Committed organized fixes.md')
  } catch (error) {
    if (verbose) logger(`Git commit failed (may be nothing to commit): ${error.message}`)
  }

  await pauseIfEnabled({ enabled: pauseMajorSteps, label: 'review', logger })

  // Update constitution based on findings
  const constitutionStep = makeOpencodeStep(
    'opencode-update-constitution',
    'Evaluate the issues found in fixes.md and suggest updates to our constitution and AGENTS.md to prevent these from happening again.',
    {
      model: fixModel,
      command: 'speckit.constitution',
      cwd: projectRoot,
      label: 'opencode-update-constitution',
    }
  )
  await executeStep(constitutionStep, { logger, verbose })

  // Commit constitution updates
  try {
    if (verbose) logger('Committing constitution updates...')
    await run('git', ['add', '-A'], { cwd: projectRoot })
    await run('git', ['commit', '-m', 'Review: updated constitution and AGENTS.md based on findings', '--allow-empty'], { cwd: projectRoot })
    if (verbose) logger('Committed constitution updates')
  } catch (error) {
    if (verbose) logger(`Git commit failed (may be nothing to commit): ${error.message}`)
  }

  await pauseIfEnabled({ enabled: pauseMajorSteps, label: 'constitution updates', logger })

  // Build and execute fix step
  const fixStep = buildFixStep({ projectRoot, fixModel })
  await executeStep(fixStep, { logger, verbose })

  // Commit the implemented fixes
  try {
    if (verbose) logger('Committing implemented fixes...')
    await run('git', ['add', '-A'], { cwd: projectRoot })
    await run('git', ['commit', '-m', 'Review: implemented fixes from fixes.md', '--allow-empty'], { cwd: projectRoot })
    if (verbose) logger('Committed implemented fixes')
  } catch (error) {
    if (verbose) logger(`Git commit failed (may be nothing to commit): ${error.message}`)
  }

  await pauseIfEnabled({ enabled: pauseMajorSteps, label: 'fix step', logger })

  // Run test suite and fix any failures
  try {
    if (verbose) logger('Running test suite...')
    await run('make', ['test-nextest'], { cwd: projectRoot, timeout: 0 })
    if (verbose) logger('Tests passed!')
  } catch (error) {
    if (verbose) logger('Tests failed, capturing output and invoking opencode to fix...')
    
    // Capture the test output
    const testResult = await execa('make', ['test-nextest'], { 
      cwd: projectRoot, 
      reject: false,
      encoding: 'utf8',
      timeout: 0
    })
    const testOutput = `${testResult.stdout}\n${testResult.stderr}`.trim()
    
    // Create fix step with test output in prompt
    const testFixStep = makeOpencodeStep(
      'opencode-fix-tests',
      `The test suite failed with the following output:\n\n${testOutput}\n\nFix all failing tests and ensure "make test-nextest" passes.`,
      {
        model: fixModel,
        cwd: projectRoot,
        label: 'opencode-fix-tests',
      }
    )
    await executeStep(testFixStep, { logger, verbose })
    
    // Commit the test fixes
    try {
      if (verbose) logger('Committing test fixes...')
      await run('git', ['add', '-A'], { cwd: projectRoot })
      await run('git', ['commit', '-m', 'Tests: fixed test failures', '--allow-empty'], { cwd: projectRoot })
      if (verbose) logger('Committed test fixes')
    } catch (error) {
      if (verbose) logger(`Git commit failed (may be nothing to commit): ${error.message}`)
    }
    
    // Verify tests pass after fixes
    if (verbose) logger('Re-running tests to verify fixes...')
    await run('make', ['test-nextest'], { cwd: projectRoot, timeout: 0 })
    if (verbose) logger('Tests now pass!')
  }

  await pauseIfEnabled({ enabled: pauseMajorSteps, label: 'test and test fixes', logger })

  // Finalize by pushing, opening, and merging a PR, then clean up.
  await pauseIfEnabled({ enabled: pauseMajorSteps, label: 'finalization (PR/cleanup)', logger })
  await finalizeWorkflow({ projectRoot, branch, logger, verbose })

  if (cleanupWorktree) {
    await cleanupWorktree({ deleteBranch: true })
    cleanupPerformed = true
  }

  return { cleanupPerformed }
}
