<script setup>
defineProps({
  steps: {
    type: Array,
    default: () => []
  },
  direction: {
    type: String,
    default: 'horizontal'
  }
})
</script>

<template>
  <div
    class="flex items-center justify-center gap-1"
    :class="direction === 'vertical' ? 'flex-col' : 'flex-row flex-wrap'"
  >
    <template v-for="(step, i) in steps" :key="i">
      <div
        class="px-2 py-1 rounded-lg font-medium text-center text-sm min-w-20"
        :class="step.class || 'bg-slate-700 text-white'"
      >
        {{ step.name }}
      </div>
      <div
        v-if="i < steps.length - 1"
        class="text-slate-500 text-base"
      >
        {{ direction === 'vertical' ? '↓' : '→' }}
      </div>
    </template>
  </div>
</template>
