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
    class="flex items-center justify-center gap-2"
    :class="direction === 'vertical' ? 'flex-col' : 'flex-row flex-wrap'"
  >
    <template v-for="(step, i) in steps" :key="i">
      <div
        class="px-4 py-2 rounded-lg font-medium text-center min-w-24"
        :class="step.class || 'bg-slate-700 text-white'"
      >
        {{ step.name }}
      </div>
      <div
        v-if="i < steps.length - 1"
        class="text-slate-500 text-xl"
      >
        {{ direction === 'vertical' ? '↓' : '→' }}
      </div>
    </template>
  </div>
</template>
