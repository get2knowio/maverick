<script setup>
defineProps({
  number: [String, Number],
  title: String,
  description: String,
  color: {
    type: String,
    default: 'indigo'
  }
})

const borderColors = {
  indigo: 'border-indigo-500',
  purple: 'border-purple-500',
  cyan: 'border-cyan-500',
  emerald: 'border-emerald-500',
  amber: 'border-amber-500',
  rose: 'border-rose-500',
  blue: 'border-blue-500',
  teal: 'border-teal-500'
}

const textColors = {
  indigo: 'text-indigo-400',
  purple: 'text-purple-400',
  cyan: 'text-cyan-400',
  emerald: 'text-emerald-400',
  amber: 'text-amber-400',
  rose: 'text-rose-400',
  blue: 'text-blue-400',
  teal: 'text-teal-400'
}
</script>

<template>
  <div
    class="p-2 rounded-lg bg-gradient-to-br from-slate-800 to-slate-900 border-l-4"
    :class="borderColors[color]"
  >
    <div class="flex items-center gap-1.5 mb-0.5">
      <span
        class="font-mono font-bold text-sm"
        :class="textColors[color]"
      >
        {{ number }}.
      </span>
      <h4 class="font-semibold text-white text-sm">{{ title }}</h4>
    </div>
    <p class="text-xs text-slate-400 leading-snug">{{ description }}</p>
    <slot></slot>
  </div>
</template>
