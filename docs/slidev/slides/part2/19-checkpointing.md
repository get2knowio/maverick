---
layout: section
class: text-center
---

# 19. Checkpointing & Resumption

<div class="text-lg text-secondary mt-4">
Saving workflow state so long-running runs can resume safely
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">5 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Checkpoint Stores</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Recovery</span>
  </div>
</div>

---
layout: two-cols
---

# 19.1 Why Checkpoints Matter

<div class="pr-4 text-sm">

Long-running workflows can fail because of:

- network/API interruptions
- process crashes or user interrupts
- agent/session failures
- expensive multi-step loops such as fly bead execution

</div>

::right::

<div class="pl-4 mt-8">

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Maverick principle</strong><br>
  Fail gracefully, recover aggressively.
  Checkpoints are what make recovery practical.
</div>

</div>

---
layout: two-cols
---

# 19.2 CheckpointStore Implementations

<div class="pr-4">

```python
class CheckpointStore(Protocol):
    async def save(...): ...
    async def load(...): ...
    async def load_latest(...): ...
    async def clear(...): ...
```

</div>

::right::

<div class="pl-4 mt-8 text-sm">

| Store | Purpose |
|-------|---------|
| `FileCheckpointStore` | durable JSON checkpoints with atomic writes |
| `MemoryCheckpointStore` | lightweight test-only storage |

</div>

---
layout: two-cols
---

# 19.3 FileCheckpointStore

<div class="pr-4">

```python
store = FileCheckpointStore()
await store.save(workflow_id, data)
```

</div>

::right::

<div class="pl-4 mt-8 text-sm">

## Characteristics

- JSON files under Maverick's checkpoint directory
- atomic write pattern prevents partial corruption
- loads latest checkpoint by <code>saved_at</code>
- cleans up orphaned temp files on startup

</div>

---
layout: default
---

# 19.4 Workflow Integration

```python
await workflow.save_checkpoint(data)
latest = await workflow.load_checkpoint()
```

<div class="mt-6 text-sm">
  Workflows decide <em>when</em> to checkpoint — typically after expensive agent work, after loop iterations, or after safe completion boundaries such as a bead commit.
</div>

<div class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm text-center">
  In FlyBeadsWorkflow, checkpointing captures progress across the bead loop so a failed run can continue instead of restarting from scratch.
</div>
