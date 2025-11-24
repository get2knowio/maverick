# Contributing to Maverick

Thank you for contributing to Maverick! This guide explains the architecture and how to extend the workflow system.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Three-Layer Design](#three-layer-design)
- [Adding New Step Types](#adding-new-step-types)
- [Adding New Workflow Steps](#adding-new-workflow-steps)
- [Extending Workflows](#extending-workflows)
- [Testing Guidelines](#testing-guidelines)
- [Code Style](#code-style)

## Architecture Overview

Maverick separates workflow concerns into three distinct layers:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Step Description (What)                       │
│  - makeShellStep(), makeOpencodeStep(), etc.            │
│  - Returns plain data objects                           │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Step Execution (How)                          │
│  - executeStep(), executeSteps()                        │
│  - Centralized logging, timing, capture                 │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Workflow Orchestration (When/Why)             │
│  - runWorkflow(), buildPhaseSteps(), etc.               │
│  - High-level flow control and business logic           │
└─────────────────────────────────────────────────────────┘
```

## Three-Layer Design

### Layer 1: Step Description Types

**Location**: Step factory modules in `src/steps/`

**Purpose**: Define *what* a step is—pure data describing the command, its arguments, and metadata.

**Two flavors**:

1. **Generic step types** (`shell.mjs`, `opencode.mjs`, `coderabbit.mjs`): Low-level building blocks that wrap commands with minimal logic. You provide the executable, args, and options.

2. **Domain-specific step types** (`speckit.mjs`): High-level workflow steps that encapsulate complete domain logic including executables, parameters, AND prompts. These represent reusable workflow patterns.

**Characteristics**:
- Returns plain JavaScript objects
- No side effects or I/O
- Easily serializable (useful for UI, debugging, persistence)
- Contains: `id`, `kind`, `label`, `cmd`, `args`, `cwd`, `captureTo`

**Example**:

```javascript
export function makeShellStep(id, cmd, args = [], opts = {}) {
  return {
    id,
    kind: 'shell',
    label: opts.label || id,
    cmd,
    args,
    cwd: opts.cwd,
    env: opts.env,
    captureTo: opts.captureTo,
  }
}
```

### Layer 2: Step Execution

**Location**: `src/workflow-core.mjs` (Step Execution section)

**Purpose**: Define *how* to execute a step descriptor—logging, timing, output capture, error handling.

**Characteristics**:
- Takes a step descriptor + execution context
- Handles all I/O and side effects
- Centralized location for execution concerns (retries, timeouts, etc.)
- Uses underlying primitives: `run()`, `runWithProgress()`, `runAndCapture()`

**Example**:

```javascript
export async function executeStep(step, { logger, verbose } = {}) {
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
```

### Layer 3: Workflow Orchestration

**Location**: `src/workflow-core.mjs` (Step Builders section + `runWorkflow`)

**Purpose**: Define *when* and *why* steps run—business logic, iteration, phase management.

**Characteristics**:
- Builds step descriptors using Layer 1 functions
- Executes steps using Layer 2 functions
- Manages workflow state (parsing tasks, checking completion, iteration)
- Contains domain-specific logic (what happens in a review phase, fix phase, etc.)

**Example**:

```javascript
function buildReviewSteps({ projectRoot, outDir, reviewModel, coderabbitPath, reviewPath }) {
  const steps = []
  
  steps.push(
    makeCoderabbitStep('coderabbit-review', ['review', '--prompt-only'], {
      cwd: projectRoot,
      captureTo: coderabbitPath,
    })
  )
  
  steps.push(
    makeOpencodeStep('opencode-review', reviewPrompt, {
      model: reviewModel,
      cwd: projectRoot,
      captureTo: reviewPath,
    })
  )
  
  return steps
}
```

## Adding New Step Types

### Generic vs Domain-Specific Steps

Before creating a new step type, decide which flavor you need:

**Generic steps** (like `makeShellStep`, `makeOpencodeStep`):
- Thin wrappers around commands
- User provides most/all arguments and options
- Reusable across many contexts
- Example: `makeShellStep('deploy', 'kubectl', ['apply', '-f', 'deployment.yaml'])`

**Domain-specific steps** (like `opencodeImplementPhase`, `coderabbitReview`):
- Encapsulate complete workflow patterns
- Embed domain knowledge (prompts, flags, conventions)
- Higher-level, purpose-built for specific use cases
- Example: `opencodeImplementPhase('2A', { cwd, model })` (prompt is built-in)

### Adding a Generic Step Type

To add support for a new type of command (e.g., `docker`, `terraform`, `ansible`):

### 1. Create a Step Factory (Layer 1)

Create a new file `src/steps/docker.mjs`:

```javascript
// src/steps/docker.mjs
import { makeStep } from './core.mjs'

/**
 * Create a docker command step descriptor.
 * @param {string} id - Unique step identifier
 * @param {string[]} args - Docker command arguments
 * @param {object} opts - Additional options (cwd, label, captureTo, env)
 */
export function makeDockerStep(id, args = [], opts = {}) {
  return makeStep({
    id,
    kind: 'docker',
    cmd: 'docker',
    args,
    cwd: opts.cwd,
    env: opts.env,
    label: opts.label,
    captureTo: opts.captureTo,
  })
}
```

### 2. Add DSL Helper (Optional)

Add to the same file (`src/steps/docker.mjs`):

```javascript
/**
 * Convenience helper to create a docker step with minimal syntax.
 */
export function dockerStep(id, args = [], opts = {}) {
  return makeDockerStep(id, args, opts)
}
```

### 3. Update executeStep (If Needed)

If your new step type requires special execution logic (beyond what `runWithProgress` and `runAndCapture` provide), update `executeStep()` in `src/steps/core.mjs`:

```javascript
export async function executeStep(step, { logger, verbose } = {}) {
  const { cmd, args = [], cwd, captureTo, label, id, kind } = step
  const tag = label || id || cmd

  if (verbose) logger(`Starting step ${tag}: ${cmd} ${args.join(' ')}`)

  // Special handling for docker steps
  if (kind === 'docker') {
    // Custom execution logic here
    return runDockerWithSpecialHandling(cmd, args, { cwd, logger, verbose })
  }

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
```

### 4. Use in Workflow

Import and use in your workflow (e.g., `src/workflows/myWorkflow.mjs`):

```javascript
import { dockerStep } from '../steps/docker.mjs'
import { executeSteps } from '../steps/core.mjs'

const steps = [
  dockerStep('build-image', ['build', '-t', 'myapp:latest', '.'], { cwd: projectRoot }),
  dockerStep('run-container', ['run', '-d', '-p', '8080:8080', 'myapp:latest']),
]

await executeSteps(steps, { logger, verbose })
```

### Adding a Domain-Specific Step Type

To add a reusable workflow pattern that encapsulates prompts and conventions:

#### 1. Add to an Existing Domain Module or Create New One

If adding to `src/steps/speckit.mjs`:

```javascript
/**
 * Create an opencode step that refactors code based on a style guide.
 * 
 * @param {string} styleGuide - Path to style guide document
 * @param {object} opts - Options
 * @param {string} opts.cwd - Working directory
 * @param {string} opts.model - Model to use
 * @returns {object} Step descriptor
 */
export function opencodeRefactorToStyle(styleGuide, opts = {}) {
  const { cwd, model = 'github-copilot/claude-sonnet-4.5' } = opts
  
  const prompt = [
    `Read the style guide at ${styleGuide}.`,
    'Refactor all code in the repository to match the style guide.',
    'Maintain functionality while improving consistency, readability, and idioms.',
    'Make incremental commits with descriptive messages.',
  ].join(' ')
  
  const args = ['run', '--model', model, prompt]
  
  return makeStep({
    id: 'opencode-refactor-style',
    kind: 'opencode-refactor',
    cmd: 'opencode',
    args,
    cwd,
    label: 'refactor-to-style-guide',
  })
}
```

Or create a new domain module `src/steps/cicd.mjs`:

```javascript
// steps/cicd.mjs
import { makeStep } from './core.mjs'

export function terraformPlan(opts = {}) {
  const { cwd, outFile = 'tfplan' } = opts
  
  return makeStep({
    id: 'terraform-plan',
    kind: 'terraform-plan',
    cmd: 'terraform',
    args: ['plan', '-out', outFile],
    cwd,
    label: 'terraform-plan',
  })
}

export function terraformApply(opts = {}) {
  const { cwd, planFile = 'tfplan' } = opts
  
  return makeStep({
    id: 'terraform-apply',
    kind: 'terraform-apply',
    cmd: 'terraform',
    args: ['apply', planFile],
    cwd,
    label: 'terraform-apply',
  })
}
```

#### 2. Use in Workflows

```javascript
import { opencodeRefactorToStyle } from '../steps/speckit.mjs'
import { terraformPlan, terraformApply } from '../steps/cicd.mjs'

const steps = [
  opencodeRefactorToStyle('docs/STYLE_GUIDE.md', { cwd: projectRoot }),
  terraformPlan({ cwd: infraDir }),
  terraformApply({ cwd: infraDir }),
]

await executeSteps(steps, { logger, verbose })
```

**Key principle**: Domain-specific steps should encode "best practices" or "standard patterns" so users don't have to remember complex prompts or flag combinations.

#### When to Use Each Approach

**Use generic steps** when:
- You need fine-grained control over arguments
- The command varies significantly across use cases
- You're prototyping a new workflow pattern

**Use domain-specific steps** when:
- You have a proven workflow pattern you want to reuse
- The prompt/arguments follow consistent conventions
- You want to hide complexity from workflow authors

**Example comparison**:

```javascript
// Generic approach - full control, more verbose
import { makeOpencodeStep } from '../steps/opencode.mjs'

const reviewPrompt = [
  'Perform a standalone, senior-level code review...',
  'Use spec.md, plan.md, and tasks.md...',
  // 5+ lines of prompt
].join(' ')

const step = makeOpencodeStep('review', reviewPrompt, {
  model: 'github-copilot/claude-sonnet-4.5',
  cwd: projectRoot,
  captureTo: 'review.md',
})

// Domain-specific approach - concise, encapsulates best practices
import { opencodeReview } from '../steps/speckit.mjs'

const step = opencodeReview({
  cwd: projectRoot,
  captureTo: 'review.md',
  model: 'github-copilot/claude-sonnet-4.5',
})
```

## Adding New Workflow Steps

To add a new step to an existing workflow:

### 1. Identify the Appropriate Builder Function

Find the step builder function that constructs the phase you want to modify:

- `buildPhaseSteps()` - Implementation phase steps
- `buildReviewSteps()` - Review phase steps  
- `buildFixStep()` - Fix phase step

### 2. Add Your Step to the Builder

Edit the appropriate workflow file (e.g., `src/workflows/default.mjs`):

```javascript
import { makeShellStep } from '../steps/shell.mjs'

function buildReviewSteps({ projectRoot, outDir, reviewModel, coderabbitPath, reviewPath }) {
  const steps = []
  
  // Existing steps...
  steps.push(makeCoderabbitStep(...))
  steps.push(makeOpencodeStep(...))
  
  // NEW: Add static analysis step
  steps.push(
    makeShellStep(
      'eslint-analysis',
      'eslint',
      ['.', '--format', 'json', '--output-file', path.join(outDir, 'eslint.json')],
      { cwd: projectRoot, label: 'eslint-static-analysis' }
    )
  )
  
  return steps
}
```

### 3. Update Workflow Orchestration (If Needed)

If your new step introduces new dependencies or requires special handling:

```javascript
// In runWorkflow()...

// Build and execute review steps (skip if files already exist)
const reviewSteps = buildReviewSteps({ projectRoot, outDir, reviewModel, coderabbitPath, reviewPath })

for (const step of reviewSteps) {
  // Custom skip logic for your new step
  if (step.id === 'eslint-analysis' && await fileExists(path.join(outDir, 'eslint.json'))) {
    if (verbose) logger('eslint.json exists; skipping eslint analysis')
    continue
  }
  
  // Check if output file exists (skip if it does)
  if (step.captureTo && await fileExists(step.captureTo)) {
    if (verbose) logger(`${step.captureTo} exists; skipping ${step.id}`)
    continue
  }
  
  await executeStep(step, { logger, verbose })
  
  // Sleep after each review step
  if (verbose) logger(`Waiting ${PHASE_SLEEP_SECONDS}s before next step...`)
  await new Promise(resolve => setTimeout(resolve, PHASE_SLEEP_SECONDS * 1000))
}
```

## Extending Workflows

To create an entirely new workflow (e.g., for a different use case):

### 1. Create a New Workflow Function

Create a new file `src/workflows/deployment.mjs`:

```javascript
import { shellStep, dockerStep } from '../steps/shell.mjs'
import { executeSteps } from '../steps/core.mjs'

export async function runDeploymentWorkflow({
  environment,
  dockerImage,
  verbose = false,
  logger = m => console.log(m)
}) {
  const steps = [
    shellStep('git-fetch', 'git', ['fetch', 'origin', 'main']),
    shellStep('git-checkout', 'git', ['checkout', 'main']),
    dockerStep('docker-pull', ['pull', dockerImage]),
    dockerStep('docker-deploy', ['stack', 'deploy', '--compose-file', 'docker-compose.yml', 'myapp']),
    shellStep('health-check', 'curl', ['-f', `https://${environment}.example.com/health`]),
  ]
  
  await executeSteps(steps, { logger, verbose }, { sleepBetween: 5 })
}
```

### 2. Create a New CLI Entry Point

Add `src/deploy.mjs`:

```javascript
#!/usr/bin/env node
import { Listr } from 'listr2'
import meow from 'meow'
import { runDeploymentWorkflow } from './workflows/deployment.mjs'

async function main() {
  const cli = meow(`
    Usage
      $ maverick-deploy [environment] [options]

    Options
      --image, -i        Docker image to deploy
      --verbose, -v      Enable verbose logging
  `, {
    importMeta: import.meta,
    flags: {
      image: { type: 'string', shortFlag: 'i' },
      verbose: { type: 'boolean', shortFlag: 'v', default: false }
    }
  })

  const environment = cli.input[0] || 'staging'
  
  await runDeploymentWorkflow({
    environment,
    dockerImage: cli.flags.image,
    verbose: cli.flags.verbose,
    logger: m => console.log(m)
  })
}

main().catch(err => {
  console.error('Deployment failed:', err)
  process.exit(1)
})
```

### 3. Update package.json

```json
{
  "bin": {
    "maverick": "src/workflow.mjs",
    "maverick-deploy": "src/deploy.mjs"
  }
}
```

## Testing Guidelines

### Unit Testing Step Factories

Test that step factories produce correct descriptors:

```javascript
import { test } from 'node:test'
import assert from 'node:assert'
import { makeShellStep } from '../src/steps/shell.mjs'

test('makeShellStep creates valid descriptor', () => {
  const step = makeShellStep('test-id', 'echo', ['hello'], { cwd: '/tmp' })
  
  assert.equal(step.id, 'test-id')
  assert.equal(step.kind, 'shell')
  assert.equal(step.cmd, 'echo')
  assert.deepEqual(step.args, ['hello'])
  assert.equal(step.cwd, '/tmp')
})
```

### Integration Testing Step Execution

Test that steps execute correctly (use mocks for expensive operations):

```javascript
import { executeStep } from '../src/steps/core.mjs'
import { makeShellStep } from '../src/steps/shell.mjs'

test('executeStep runs command with correct context', async () => {
  const logs = []
  const step = makeShellStep('test', 'echo', ['test'])
  
  await executeStep(step, { 
    logger: m => logs.push(m), 
    verbose: true 
  })
  
  assert(logs.some(l => l.includes('Starting step test')))
})
```

### End-to-End Workflow Testing

Create fixture `tasks.md` files and test full workflow execution:

```javascript
import { runDefaultWorkflow } from '../src/workflows/default.mjs'

test('runDefaultWorkflow completes all phases', async () => {
  const result = await runDefaultWorkflow({
    branch: 'test-branch',
    phases: mockPhases,
    tasksPath: './fixtures/test-tasks.md',
    verbose: false,
    logger: () => {}
  })
  
  // Assert expected outcomes
})
```

## Code Style

### General Principles

1. **Pure functions where possible**: Keep Layer 1 (step factories) side-effect-free
2. **Single Responsibility**: Each function should do one thing well
3. **Explicit over implicit**: Prefer named parameters over positional when more than 2 args
4. **Document public APIs**: Use JSDoc for all exported functions
5. **Error handling**: Let errors bubble up; handle at orchestration layer

### Naming Conventions

- **Step factories**: `make*Step` (e.g., `makeShellStep`)
- **DSL helpers**: `*Step` (e.g., `shellStep`)
- **Execution functions**: `execute*` or `run*` (e.g., `executeStep`, `runWorkflow`)
- **Builder functions**: `build*Steps` (e.g., `buildPhaseSteps`)
- **Internal helpers**: Plain descriptive names (e.g., `fileExists`, `parsePhases`)

### File Organization

**`src/steps/core.mjs`**:
- Step descriptor factory (`makeStep`)
- Step execution (`executeStep`, `executeSteps`)
- Execution primitives (`run`, `runAndCapture`, `runWithProgress`)

**`src/steps/shell.mjs`**:
- `makeShellStep`, `shellStep`

**`src/steps/opencode.mjs`**:
- `makeOpencodeStep`, `opencodeStep`

**`src/steps/coderabbit.mjs`**:
- `makeCoderabbitStep`, `coderabbitStep`

**`src/steps/speckit.mjs`** (domain-specific workflow steps):
- `opencodeImplementPhase` - Implement tasks for a specific phase
- `coderabbitReview` - CodeRabbit review with --prompt-only
- `opencodeReview` - Opencode senior-level code review
- `opencodeFix` - Address issues from review feedback

**`src/tasks/markdown.mjs`**:
- `parsePhases` - Parse markdown task files
- `fileExists` - Check file existence
- Internal helpers for task extraction and counting

**`src/workflows/default.mjs`**:
- Constants (`PHASE_SLEEP_SECONDS`)
- Step builders (`buildPhaseSteps`, `buildReviewSteps`, `buildFixStep`)
- Workflow orchestration (`runDefaultWorkflow`)

**`src/workflow.mjs`** (CLI entry point):
- CLI argument parsing with `meow`
- Task list setup with Listr2
- Workflow invocation

### JSDoc Standards

All exported functions must have JSDoc comments:

```javascript
/**
 * Create a shell command step descriptor.
 * @param {string} id - Unique step identifier
 * @param {string} cmd - Command executable
 * @param {string[]} args - Command arguments
 * @param {object} opts - Additional options (cwd, env, label, captureTo)
 * @returns {object} Step descriptor
 */
export function makeShellStep(id, cmd, args = [], opts = {}) {
  // ...
}
```

## Questions?

If you have questions or need clarification on any of these patterns:

1. Check the existing code for examples
2. Look at how similar step types are implemented
3. Open an issue for discussion

Thank you for contributing to Maverick!
