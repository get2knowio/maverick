# Quickstart: Built-in Workflow Library

**Branch**: `025-builtin-workflow-library` | **Date**: 2025-12-20

## Overview

Maverick ships with a library of built-in workflows for common development tasks. This guide shows how to use, customize, and extend these workflows.

---

## Using Built-in Workflows

### List Available Workflows

```bash
# List all discovered workflows (built-in + user + project)
maverick workflow list

# Output:
# Name       Version  Source    Description
# fly        1.0      builtin   Full spec-based development workflow
# refuel     1.0      builtin   Tech-debt resolution workflow
# review     1.0      builtin   Code review orchestration workflow
# validate   1.0      builtin   Validation with optional fixes
# quick_fix  1.0      builtin   Quick issue fix workflow
```

### Show Workflow Details

```bash
# Show workflow inputs and steps
maverick workflow show fly

# Output:
# Workflow: fly
# Version: 1.0
# Description: Full spec-based development workflow
#
# Inputs:
#   branch_name (string, required) - Feature branch name
#   task_file (string, optional) - Path to tasks.md
#   skip_review (boolean, optional, default: false) - Skip code review stage
#
# Steps (6):
#   1. init (python)
#   2. implement (agent)
#   3. validate-and-fix (subworkflow)
#   4. commit-and-push (subworkflow)
#   5. review (agent)
#      when: ${{ !inputs.skip_review }}
#   6. create-pr (subworkflow)
```

### Run a Built-in Workflow

```bash
# Run the fly workflow
maverick workflow run fly -i branch_name=feature-123

# Run with optional inputs
maverick workflow run fly -i branch_name=feature-123 -i skip_review=true

# Run validate workflow with fix enabled
maverick workflow run validate -i fix=true -i max_attempts=5

# Run quick_fix for a specific issue
maverick workflow run quick_fix -i issue_number=42

# Dry run (show execution plan without running)
maverick workflow run fly -i branch_name=feature-123 --dry-run
```

---

## Customizing Built-in Workflows

### Override with Project Workflow

Create a workflow with the same name in your project to override:

```bash
# Create project workflows directory
mkdir -p .maverick/workflows

# Copy the built-in for customization
maverick workflow show fly --format yaml > .maverick/workflows/fly.yaml

# Edit to customize
# Now your project's fly.yaml takes precedence
```

Example customization (`.maverick/workflows/fly.yaml`):

```yaml
version: "1.0"
name: fly
description: Customized fly workflow for our team

inputs:
  branch_name:
    type: string
    required: true
    description: Feature branch name
  skip_review:
    type: boolean
    required: false
    default: true  # Our team skips review by default

steps:
  - name: init
    type: python
    action: init_workspace

  - name: implement
    type: agent
    agent: implementer
    context: implementation_context

  - name: validate-and-fix
    type: subworkflow
    workflow: validate_and_fix
    inputs:
      max_attempts: 5  # More retries than default

  - name: commit-and-push
    type: subworkflow
    workflow: commit_and_push

  # Removed review step for our workflow

  - name: create-pr
    type: subworkflow
    workflow: create_pr_with_summary
    inputs:
      draft: true  # Always create as draft
```

### Override with User Workflow

For personal customizations that apply across all projects:

```bash
# Create user workflows directory
mkdir -p ~/.config/maverick/workflows

# Create custom workflow
cat > ~/.config/maverick/workflows/validate.yaml << 'EOF'
version: "1.0"
name: validate
description: My personal validation workflow

inputs:
  fix:
    type: boolean
    required: false
    default: true
  max_attempts:
    type: integer
    required: false
    default: 10  # I want more retries

steps:
  - name: run-validation
    type: validate
    stages: ["format", "lint", "typecheck"]  # Skip tests
    retry: ${{ inputs.max_attempts }}
EOF
```

---

## Creating New Workflows

### Using Templates

```bash
# Create a basic workflow
maverick workflow new my-workflow --template basic

# Create a full workflow with validation/review/PR
maverick workflow new feature-flow --template full

# Create a parallel workflow example
maverick workflow new batch-processor --template parallel

# Create as Python instead of YAML
maverick workflow new my-workflow --template basic --format python

# Specify output directory
maverick workflow new my-workflow --output-dir ./workflows
```

### Basic Template Example

Generated file `.maverick/workflows/my-workflow.yaml`:

```yaml
version: "1.0"
name: my-workflow
description: A basic workflow template

# Define your workflow inputs here
inputs:
  example_input:
    type: string
    required: true
    description: An example input parameter

steps:
  # Step 1: Initialize
  - name: init
    type: python
    action: example_init
    kwargs:
      param: ${{ inputs.example_input }}

  # Step 2: Main processing
  - name: process
    type: agent
    agent: processor
    context:
      data: ${{ steps.init.output }}

  # Step 3: Finalize
  - name: finalize
    type: python
    action: example_finalize
```

### Full Template Example

Generated file includes validation, review, and PR creation patterns:

```yaml
version: "1.0"
name: feature-flow
description: A complete workflow with validation, review, and PR

inputs:
  branch_name:
    type: string
    required: true
    description: Feature branch name
  skip_review:
    type: boolean
    required: false
    default: false

steps:
  - name: setup
    type: python
    action: setup_branch
    kwargs:
      branch: ${{ inputs.branch_name }}

  - name: implement
    type: agent
    agent: implementer
    context: implementation_context

  - name: validate
    type: subworkflow
    workflow: validate_and_fix
    inputs:
      max_attempts: 3

  - name: commit
    type: subworkflow
    workflow: commit_and_push

  - name: review
    type: agent
    agent: code_reviewer
    context: review_context
    when: ${{ !inputs.skip_review }}

  - name: create-pr
    type: subworkflow
    workflow: create_pr_with_summary
```

---

## Using Fragments

Fragments are reusable sub-workflows for common patterns.

### Available Fragments

| Fragment | Purpose | Used By |
|----------|---------|---------|
| `validate_and_fix` | Validation-with-retry loop | fly, refuel, validate |
| `commit_and_push` | Generate commit, commit, push | fly, refuel, quick_fix |
| `create_pr_with_summary` | Generate PR body, create PR | fly, refuel, quick_fix |

### Invoking a Fragment

```yaml
steps:
  - name: my-validation
    type: subworkflow
    workflow: validate_and_fix
    inputs:
      stages:
        - format
        - lint
        - typecheck
        - test
      max_attempts: 5
      fixer_agent: custom_fixer
```

### Overriding Fragments

Create a fragment with the same name to customize:

```yaml
# .maverick/workflows/validate_and_fix.yaml
version: "1.0"
name: validate_and_fix
description: Custom validation fragment for our project

inputs:
  stages:
    type: array
    required: false
    default: ["format", "lint"]  # Simplified stages
  max_attempts:
    type: integer
    required: false
    default: 2

steps:
  - name: run-checks
    type: validate
    stages: ${{ inputs.stages }}
    retry: ${{ inputs.max_attempts }}
```

---

## Discovery Precedence

Workflows are discovered from multiple locations with precedence:

| Priority | Location | Purpose |
|----------|----------|---------|
| 1 (highest) | `.maverick/workflows/` | Project-specific |
| 2 | `~/.config/maverick/workflows/` | User preferences |
| 3 (lowest) | Built-in library | Default workflows |

Higher priority workflows override lower priority ones with the same name.

### Checking Active Workflow Source

```bash
# Show which source a workflow comes from
maverick workflow show fly

# Output includes:
# Source: project  (or "user" or "builtin")
# File: .maverick/workflows/fly.yaml
# Overrides: builtin:fly
```

---

## Troubleshooting

### Workflow Not Found

```bash
# Check available workflows
maverick workflow list

# Ensure workflow file is in correct location
ls .maverick/workflows/
ls ~/.config/maverick/workflows/
```

### Conflict Error

If you see "Multiple workflows named 'X' at Y level":

```bash
# You have two files with same workflow name at same precedence
# Remove or rename one of them
ls .maverick/workflows/*.yaml
```

### Invalid Workflow File

If a workflow fails to load, it's logged as a warning:

```bash
# Run with verbose mode to see skipped files
maverick -v workflow list

# Output includes warnings like:
# WARNING: Skipping invalid workflow .maverick/workflows/broken.yaml: ...
```

### Visualization

```bash
# Generate ASCII diagram
maverick workflow viz fly

# Generate Mermaid diagram for documentation
maverick workflow viz fly --format mermaid --output docs/fly-diagram.md
```

---

## Next Steps

1. **Explore built-in workflows**: `maverick workflow show <name>`
2. **Create custom workflow**: `maverick workflow new my-workflow`
3. **Override for your project**: Copy and modify in `.maverick/workflows/`
4. **Read the DSL guide**: [Workflow DSL Documentation](../022-workflow-dsl/spec.md)
