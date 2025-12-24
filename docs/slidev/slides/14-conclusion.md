# Part 14: Future & Conclusion

---
layout: center
class: text-center
---

# How Maverick Was Built
## Spec-Driven Development in Action

---

# 26 Specifications, Incrementally Built

<div class="grid grid-cols-2 gap-8 mt-8">

<div v-click>

### Foundation (001-002)
- Project structure & config
- MaverickAgent base class
- Claude SDK integration

### Specialized Agents (003-004)
- CodeReviewerAgent
- ImplementerAgent
- IssueFixerAgent

### Tools & Safety (005-007)
- GitHub MCP tools
- Utility tools (git, notifications)
- Safety hooks & logging

</div>

<div v-click>

### Core Workflows (008-010)
- Validation workflow
- FlyWorkflow (spec-based)
- RefuelWorkflow (tech-debt)

### User Interface (011-014)
- TUI layout & theming
- Workflow widgets
- Interactive screens
- CLI entry point

### Infrastructure (015-018)
- Testing framework
- Git operations
- Subprocess runners
- Context builder

</div>

</div>

<div v-click class="mt-8 text-center">

### Advanced Features (019-026)
Generator agents • Workflow refactor • Tool permissions • DSL engine • Flow control • Serialization • Built-in library

</div>

<div v-click class="mt-4 p-4 bg-blue-500/10 rounded">

**Key Insight**: Each spec builds on previous ones, creating a coherent architecture through disciplined incremental development.

</div>

---

# Key Takeaways

<div class="space-y-6 mt-8">

<div v-click class="flex items-start gap-4">
<div class="text-3xl">1️⃣</div>
<div>
<h3 class="text-xl font-bold">Separation of Concerns</h3>
<p class="text-gray-400">Agents know <em>HOW</em> to do tasks. Workflows know <em>WHAT</em> and <em>WHEN</em>. TUI presents state. Clear boundaries prevent tangled complexity.</p>
</div>
</div>

<div v-click class="flex items-start gap-4">
<div class="text-3xl">2️⃣</div>
<div>
<h3 class="text-xl font-bold">Constrained Tools</h3>
<p class="text-gray-400">Principle of least privilege. Each agent gets exactly the tools it needs—no more. Prevents overreach and unexpected side effects.</p>
</div>
</div>

<div v-click class="flex items-start gap-4">
<div class="text-3xl">3️⃣</div>
<div>
<h3 class="text-xl font-bold">Python + Claude = Power</h3>
<p class="text-gray-400">Deterministic orchestration (Python) + AI judgment (Claude). Best of both worlds: reliability meets adaptability.</p>
</div>
</div>

<div v-click class="flex items-start gap-4">
<div class="text-3xl">4️⃣</div>
<div>
<h3 class="text-xl font-bold">Fail Forward</h3>
<p class="text-gray-400">Resilience through retries, checkpoints, and graceful degradation. One failure doesn't crash the entire workflow.</p>
</div>
</div>

<div v-click class="flex items-start gap-4">
<div class="text-3xl">5️⃣</div>
<div>
<h3 class="text-xl font-bold">Extensibility First</h3>
<p class="text-gray-400">Registry pattern, DSL, custom workflows. Built for your specific needs, not just ours.</p>
</div>
</div>

</div>

---
layout: end
class: text-center
---

# Resources & Next Steps

<div class="grid grid-cols-2 gap-12 mt-12 text-left">

<div v-click>

## Resources

**GitHub Repository**
[github.com/get2knowio/maverick](https://github.com/get2knowio/maverick)

**Project Constitution**
`.specify/memory/constitution.md`

**Contributing Guide**
`CONTRIBUTING.md`

**Documentation**
`docs/` - Architecture, workflows, agents

</div>

<div v-click>

## Getting Help

**Issue Tracker**
Report bugs or request features

**Discussions**
Ask questions, share workflows

**Community**
Join other Maverick users building better development workflows

</div>

</div>

<div v-click class="mt-12 p-6 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-lg">

### Start Your Journey

```bash
# Install with uv (recommended)
git clone https://github.com/get2knowio/maverick.git && cd maverick
uv sync && uv run maverick --help

# Or install as a tool
uv tool install .
maverick fly        # Run spec-based workflow
maverick refuel     # Fix tech-debt
```

</div>

<div v-click class="mt-8 text-2xl">

**Thank you!** Questions?

</div>
