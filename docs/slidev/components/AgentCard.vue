<script setup>
defineProps({
  name: String,
  type: {
    type: String,
    default: 'implementer'
  },
  description: String,
  tools: {
    type: Array,
    default: () => []
  }
})

const typeColors = {
  implementer: 'from-cyan-500/20 to-cyan-600/10 border-cyan-500',
  reviewer: 'from-purple-500/20 to-purple-600/10 border-purple-500',
  fixer: 'from-amber-500/20 to-amber-600/10 border-amber-500',
  generator: 'from-emerald-500/20 to-emerald-600/10 border-emerald-500'
}

const badgeColors = {
  implementer: 'bg-cyan-500/30 text-cyan-300',
  reviewer: 'bg-purple-500/30 text-purple-300',
  fixer: 'bg-amber-500/30 text-amber-300',
  generator: 'bg-emerald-500/30 text-emerald-300'
}
</script>

<template>
  <div
    class="p-2 rounded-xl bg-gradient-to-br border-l-4 transition-all hover:scale-102"
    :class="typeColors[type]"
  >
    <div class="flex items-center justify-between mb-1">
      <h3 class="font-bold text-sm text-white">{{ name }}</h3>
      <span
        class="px-1.5 py-0.5 rounded-full text-xs font-medium"
        :class="badgeColors[type]"
      >
        {{ type }}
      </span>
    </div>
    <p class="text-xs text-slate-300 mb-2 leading-snug">{{ description }}</p>
    <div v-if="tools.length" class="flex flex-wrap gap-1">
      <span
        v-for="tool in tools"
        :key="tool"
        class="px-1.5 py-0.5 bg-slate-700/50 rounded text-xs text-slate-400"
      >
        {{ tool }}
      </span>
    </div>
    <slot></slot>
  </div>
</template>
