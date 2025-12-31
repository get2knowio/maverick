<script setup>
defineProps({
  name: String,
  status: {
    type: String,
    default: 'pending',
    validator: (v) => ['pending', 'active', 'complete', 'failed'].includes(v)
  },
  description: String
})

const statusIcons = {
  pending: '○',
  active: '◉',
  complete: '✓',
  failed: '✗'
}

const statusClasses = {
  pending: 'bg-slate-700/50 text-slate-400 border-slate-600',
  active: 'bg-indigo-500/20 text-indigo-300 border-indigo-500 animate-pulse',
  complete: 'bg-green-500/20 text-green-300 border-green-500',
  failed: 'bg-red-500/20 text-red-300 border-red-500'
}
</script>

<template>
  <div
    class="flex items-center gap-2 px-2 py-1 rounded-lg border transition-all"
    :class="statusClasses[status]"
  >
    <span class="text-base font-mono">{{ statusIcons[status] }}</span>
    <div>
      <div class="font-semibold text-sm">{{ name }}</div>
      <div v-if="description" class="text-xs opacity-70 leading-tight">{{ description }}</div>
    </div>
  </div>
</template>
