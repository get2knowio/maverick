# Migration Guide: Modular Structure

## What Changed

Maverick has been refactored from a monolithic `workflow-core.mjs` into a modular, extensible architecture. The old file still exists for backward compatibility but is now just a re-export layer.

## New Module Structure

```
src/
├── steps/
│   ├── core.mjs          # Step execution engine
│   ├── shell.mjs         # Shell command steps
│   ├── opencode.mjs      # OpenAI Codex steps
│   └── coderabbit.mjs    # CodeRabbit review steps
├── tasks/
│   └── markdown.mjs      # Task file parsing
├── workflows/
│   └── default.mjs       # Default workflow implementation
├── workflow-core.mjs     # DEPRECATED: Backward compatibility re-exports
└── workflow.mjs          # CLI entry point
```

## Migration Path

### Option 1: No Changes Required (Backward Compatible)

Existing code importing from `workflow-core.mjs` will continue to work:

```javascript
// Still works! (but deprecated)
import { 
  makeShellStep, 
  executeStep, 
  parsePhases, 
  runWorkflow 
} from './workflow-core.mjs'
```

### Option 2: Migrate to New Structure (Recommended)

Update imports to use the new modular structure:

```javascript
// Before
import { makeShellStep, executeStep } from './workflow-core.mjs'

// After
import { makeShellStep } from './steps/shell.mjs'
import { executeStep } from './steps/core.mjs'
```

```javascript
// Before
import { parsePhases } from './workflow-core.mjs'

// After
import { parsePhases } from './tasks/markdown.mjs'
```

```javascript
// Before
import { runWorkflow } from './workflow-core.mjs'

// After
import { runDefaultWorkflow } from './workflows/default.mjs'
```

```javascript
// Domain-specific steps (new in modular structure)
import { 
  opencodeImplementPhase,
  coderabbitReview,
  opencodeReview,
  opencodeFix 
} from './steps/speckit.mjs'
```

## Benefits of New Structure

### 1. Clearer Boundaries

Each module has a single, well-defined responsibility:
- **Step types** only know how to create descriptors
- **Step execution** only knows how to run commands
- **Workflows** only know how to orchestrate steps
- **Task parsing** only knows how to read task files

### 2. Easier Testing

Test each concern in isolation:

```javascript
// Test step creation without execution
import { makeShellStep } from './steps/shell.mjs'
const step = makeShellStep('test', 'echo', ['hello'])
assert.equal(step.cmd, 'echo')

// Test execution without specific step types
import { executeStep } from './steps/core.mjs'
await executeStep(genericStep, { logger, verbose: true })
```

### 3. Domain-Specific Steps

The new architecture introduces **domain-specific steps** that encapsulate not just executables but also parameters, flags, and prompts:

**Before** (building prompts manually):
```javascript
const reviewPrompt = [
  'Perform a standalone, senior-level code review...',
  'Use spec.md, plan.md, and tasks.md...',
  'Provide actionable findings...',
  // ... many lines of prompt construction
].join(' ')

const step = makeOpencodeStep('review', reviewPrompt, {
  model: reviewModel,
  cwd: projectRoot,
  captureTo: reviewPath,
})
```

**After** (using domain-specific steps):
```javascript
import { opencodeReview } from './steps/speckit.mjs'

const step = opencodeReview({
  cwd: projectRoot,
  captureTo: reviewPath,
  model: reviewModel,
})
// Prompt is encapsulated inside opencodeReview()
```

**Available domain-specific steps**:
- `opencodeImplementPhase(phaseId, opts)` - Implement tasks for a phase
- `coderabbitReview(opts)` - CodeRabbit review with --prompt-only
- `opencodeReview(opts)` - Senior-level code review
- `opencodeFix(opts)` - Address review feedback

These steps are reusable across workflows and encode best practices for speckit automation.

### 4. External Extensibility

Users can now:

**Add custom step types** without modifying core files:

```javascript
// my-custom-steps/terraform.mjs
import { makeStep } from '@get2knowio/maverick/steps/core.mjs'

export function makeTerraformStep(id, args = [], opts = {}) {
  return makeStep({
    id,
    kind: 'terraform',
    cmd: 'terraform',
    args,
    cwd: opts.cwd,
    label: opts.label,
    captureTo: opts.captureTo,
  })
}
```

**Add custom workflows** without touching default workflow:

```javascript
// my-workflows/deploy.mjs
import { executeSteps } from '@get2knowio/maverick/steps/core.mjs'
import { makeShellStep } from '@get2knowio/maverick/steps/shell.mjs'
import { makeTerraformStep } from '../my-custom-steps/terraform.mjs'

export async function runDeployWorkflow(config) {
  const steps = [
    makeTerraformStep('plan', ['plan', '-out=tfplan']),
    makeTerraformStep('apply', ['apply', 'tfplan']),
    makeShellStep('health-check', 'curl', ['-f', config.healthEndpoint]),
  ]
  
  await executeSteps(steps, { logger: config.logger, verbose: config.verbose })
}
```

### 4. Package Publishing Ready

The modular structure makes it easy to publish as an npm package:

```javascript
// External projects can import specific modules
import { executeStep } from '@get2knowio/maverick/steps/core'
import { makeShellStep } from '@get2knowio/maverick/steps/shell'
import { runDefaultWorkflow } from '@get2knowio/maverick/workflows/default'
```

## Timeline

- **Now**: Both old and new APIs work (backward compatible)
- **Future**: The `workflow-core.mjs` re-export layer may be removed in a major version bump
- **Recommendation**: Migrate to new imports at your convenience

## Questions?

See [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed documentation on the new architecture.
