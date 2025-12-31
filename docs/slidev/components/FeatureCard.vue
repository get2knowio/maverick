<script setup>
defineProps({
  icon: String,
  title: String,
  description: String
})
</script>

<template>
  <div class="p-2 rounded-xl bg-slate-800/50 border border-slate-700 hover:border-indigo-500 transition-all">
    <div class="flex items-center gap-2 mb-1">
      <span v-if="icon" class="text-lg">{{ icon }}</span>
      <h3 class="font-semibold text-white text-sm">{{ title }}</h3>
    </div>
    <p class="text-xs text-slate-400 leading-snug">{{ description }}</p>
    <slot></slot>
  </div>
</template>
