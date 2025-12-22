<script setup>
defineProps({
  title: String,
  description: String,
  color: {
    type: String,
    default: 'indigo'
  },
  icon: String
})

const colorClasses = {
  indigo: 'bg-indigo-500/20 border-indigo-500 text-indigo-300',
  purple: 'bg-purple-500/20 border-purple-500 text-purple-300',
  cyan: 'bg-cyan-500/20 border-cyan-500 text-cyan-300',
  emerald: 'bg-emerald-500/20 border-emerald-500 text-emerald-300',
  amber: 'bg-amber-500/20 border-amber-500 text-amber-300'
}
</script>

<template>
  <div
    class="p-4 rounded-lg border-2 transition-all hover:scale-105"
    :class="colorClasses[color]"
  >
    <div class="flex items-center gap-2 mb-2">
      <span v-if="icon" class="text-2xl">{{ icon }}</span>
      <h3 class="font-bold text-lg">{{ title }}</h3>
    </div>
    <p class="text-sm opacity-80">{{ description }}</p>
    <slot></slot>
  </div>
</template>
