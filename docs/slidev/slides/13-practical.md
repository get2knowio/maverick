# Part 13: Practical Usage

---
layout: default
---

# Installation & Setup

Complete setup process for Maverick

<div class="grid grid-cols-2 gap-4">

<div>

## Prerequisites

<v-click>

- **Python 3.10+** installed
- **GitHub CLI** (`gh`) authenticated
- **Claude API key** from Anthropic

</v-click>

<v-click>

## Installation

```bash
# Clone repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install with pip
pip install -e .

# Or with uv (recommended)
uv pip install -e .
```

</v-click>

</div>

<div>

<v-click>

## Configuration

```bash
# Set API key
export ANTHROPIC_API_KEY=your-key-here

# Initialize config
maverick config init
```

</v-click>

<v-click>

**Config locations**:
- Project: `maverick.yaml` (version controlled)
- User: `~/.config/maverick/config.yaml` (local)

</v-click>

<v-click>

```yaml
# Example maverick.yaml
validation:
  timeout: 300
  parallel: true
workflows:
  max_agents: 3
notifications:
  enabled: true
```

</v-click>

</div>

</div>

---
layout: default
---

# Writing Effective tasks.md

Best practices for task file structure

<div class="grid grid-cols-2 gap-4">

<div>

## Good Task File Example

```markdown
# Feature: User Authentication

## Tasks

1. Create User model with email, password_hash,
   created_at fields
   - Use SQLAlchemy ORM
   - Add unique constraint on email

2. P: Add login endpoint at POST /api/auth/login
   - Validate credentials
   - Return JWT token

3. P: Add register endpoint at POST /api/auth/register
   - Hash password with bcrypt
   - Send welcome email

4. Write integration tests for auth endpoints
   - Test login success/failure
   - Test registration validation
```

</div>

<div>

<v-click>

## Key Tips

**Parallelization**
- Use `P:` prefix for independent tasks
- Agents run parallel tasks concurrently
- Saves time on large features

</v-click>

<v-click>

**Be Specific**
- Include technology choices
- Specify endpoints, paths, names
- Add acceptance criteria

</v-click>

<v-click>

**Task Granularity**
- One clear objective per task
- Break down complex work
- Tasks should take < 30 minutes each

</v-click>

<v-click>

**Dependencies**
- Order tasks logically
- Non-parallel tasks run sequentially
- Model creation before API endpoints

</v-click>

</div>

</div>

---
layout: default
---

# Best Practices

Practical tips for real-world usage

<div class="grid grid-cols-2 gap-4">

<div>

## Configuration Tips

<v-click>

**Validation Timeouts**
```yaml
validation:
  timeout: 300  # 5 min for small projects
  timeout: 900  # 15 min for large test suites
```

</v-click>

<v-click>

**Agent Limits**
```yaml
workflows:
  max_agents: 3  # Conservative for rate limits
  max_agents: 5  # If you have higher limits
```

</v-click>

<v-click>

**Team Consistency**
- Use project-level `maverick.yaml`
- Version control configuration
- Document team conventions in CLAUDE.md

</v-click>

</div>

<div>

<v-click>

## Workflow Tips

**Development Iteration**
```bash
# Preview before executing
maverick fly --dry-run

# Skip PR creation during dev
maverick fly --skip-pr

# Monitor progress
maverick status
```

</v-click>

<v-click>

## Common Pitfalls

**Branch Sync Issues**
- Always sync with main before starting
- Workflow auto-syncs by default
- Prevents merge conflicts

</v-click>

<v-click>

**Task File Size**
- Split large features into smaller specs
- Keep tasks.md under 20 tasks
- Use multiple workflow runs

</v-click>

<v-click>

**Missing Conventions**
- Create CLAUDE.md with project patterns
- Agents use it for consistency
- Update after major changes

</v-click>

</div>

</div>
