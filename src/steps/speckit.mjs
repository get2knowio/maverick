// steps/speckit.mjs
// Domain-specific step types for speckit workflow automation
// These build on generic step types to encapsulate complete workflow patterns
import { makeOpencodeStep } from './opencode.mjs'
import { makeCoderabbitStep } from './coderabbit.mjs'
import { makeCodexStep } from './codex.mjs'

/**
 * Create an opencode step that implements tasks for a specific phase.
 * Automatically constructs the appropriate prompt and command options.
 * 
 * @param {string} phaseIdentifier - Phase identifier from tasks.md (e.g., "1", "2A")
 * @param {object} opts - Options
 * @param {string} opts.cwd - Working directory
 * @param {string} opts.model - Model to use (default: github-copilot/claude-sonnet-4.5)
 * @param {number} opts.outstandingTasks - Number of outstanding tasks (for logging)
 * @param {number} opts.totalTasks - Total tasks in phase (for logging)
 * @param {string} opts.phaseTitle - Human-readable phase title (for logging)
 * @returns {object} Step descriptor
 */
export function opencodeImplementPhase(phaseIdentifier, opts = {}) {
  const {
    cwd,
    model = 'github-copilot/claude-sonnet-4.5',
    outstandingTasks,
    totalTasks,
    phaseTitle,
  } = opts

  const prompt =
    `implement phase ${phaseIdentifier} tasks, ` +
    'updating tasks.md as you complete each task. Do not stop until all the tasks for this phase have been completed.'

  const labelSuffix = outstandingTasks && totalTasks 
    ? ` (${outstandingTasks}/${totalTasks} outstanding)`
    : ''

  return makeOpencodeStep(
    `phase-${phaseIdentifier}`,
    prompt,
    {
      model,
      command: 'speckit.implement',
      cwd,
      label: `phase-${phaseIdentifier}${labelSuffix}`,
    }
  )
}

/**
 * Create a codex step that performs a senior-level code review.
 * Generates findings and adds them to fixes.md as a task list.
 * 
 * @param {object} opts - Options
 * @param {string} opts.cwd - Working directory
 * @returns {object} Step descriptor
 */
export function codexReview(opts = {}) {
  const { cwd } = opts

  const prompt = [
    'Perform a standalone, senior-level code review of this repository, measuring both quality and completeness.',
    'Use spec.md, plan.md, and tasks.md in the current speckit spec directory as guidance.',
    'Provide actionable findings with severity, rationale, and concrete fixes.',
    'Include file paths and line ranges when possible. Do not make changes.',
    'Format your findings as a series of prompts and add them as a task list to "fixes.md" in the current speckit directory.'
  ].join(' ')

  return makeCodexStep(
    'codex-review',
    prompt,
    {
      model: 'gpt-5.1-codex',
      cwd,
      dangerouslyBypassApprovalsAndSandbox: true,
      label: 'codex-review',
    }
  )
}

/**
 * Create a codex step that runs coderabbit review and adds results to fixes.md.
 * 
 * @param {object} opts - Options
 * @param {string} opts.cwd - Working directory
 * @returns {object} Step descriptor
 */
export function codexCoderabbitReview(opts = {}) {
  const { cwd } = opts

  const prompt = [
    'Execute "coderabbit review --prompt-only" and format those prompt results',
    'as additional task items in "fixes.md" in the current spec directory.'
  ].join(' ')

  return makeCodexStep(
    'codex-coderabbit-review',
    prompt,
    {
      model: 'gpt-5.1-codex-mini',
      cwd,
      dangerouslyBypassApprovalsAndSandbox: true,
      label: 'codex-coderabbit-review',
    }
  )
}

/**
 * Create a codex step that organizes and parallelizes tasks in fixes.md.
 * 
 * @param {object} opts - Options
 * @param {string} opts.cwd - Working directory
 * @returns {object} Step descriptor
 */
export function codexOrganizeFixes(opts = {}) {
  const { cwd } = opts

  const prompt = [
    'Read fixes.md in the current spec directory and organize the tasks into a proper linear sequence',
    'while optimizing opportunities for parallelization.',
    'Then, for adjacent tasks which can be addressed in parallel, prefix the prompt with a [P]',
    'so that a later process will know which work can be parallelized.',
    'Update fixes.md with this re-ordering and parallelization indicator.'
  ].join(' ')

  return makeCodexStep(
    'codex-organize-fixes',
    prompt,
    {
      model: 'gpt-5.1-codex-mini',
      cwd,
      dangerouslyBypassApprovalsAndSandbox: true,
      label: 'codex-organize-fixes',
    }
  )
}

/**
 * Create an opencode step that addresses fixes from fixes.md.
 * Reads fixes.md and executes each task serially, with parallel execution for [P] tasks.
 * 
 * @param {object} opts - Options
 * @param {string} opts.cwd - Working directory
 * @param {string} opts.model - Model to use (default: github-copilot/claude-sonnet-4.5)
 * @returns {object} Step descriptor
 */
export function opencodeFix(opts = {}) {
  const {
    cwd,
    model = 'github-copilot/claude-sonnet-4.5',
  } = opts

  const prompt = [
    'Read fixes.md in the current spec directory and serially invoke each open task as a prompt in a subagent.',
    'Adjacent tasks that are denoted with a [P] can be addressed in parallel, each in their own subagent.',
    'Update fixes.md to mark completed tasks to track your progress.'
  ].join(' ')

  return makeOpencodeStep(
    'opencode-fix-issues',
    prompt,
    {
      model,
      cwd,
      label: 'opencode-fix-issues',
    }
  )
}
