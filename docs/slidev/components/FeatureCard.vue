<script setup>
defineProps({
  icon: String,
  title: String,
  description: String
})
</script>

<template>
  <div class="p-4 rounded-xl bg-slate-800/50 border border-slate-700 hover:border-indigo-500 transition-all">
    <div class="flex items-center gap-3 mb-2">
      <span v-if="icon" class="text-2xl">{{ icon }}</span>
      <h3 class="font-semibold text-white">{{ title }}</h3>
    </div>
    <p class="text-sm text-slate-400">{{ description }}</p>
    <slot></slot>
  </div>
</template>
