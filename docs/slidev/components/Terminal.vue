<script setup>
defineProps({
  commands: {
    type: Array,
    default: () => []
  }
})
</script>

<template>
  <div class="font-mono text-sm bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
    <div class="flex items-center gap-2 px-4 py-2 bg-slate-800 border-b border-slate-700">
      <span class="w-3 h-3 rounded-full bg-red-500"></span>
      <span class="w-3 h-3 rounded-full bg-yellow-500"></span>
      <span class="w-3 h-3 rounded-full bg-green-500"></span>
      <span class="ml-2 text-slate-400 text-xs">terminal</span>
    </div>
    <div class="p-2 space-y-1">
      <div v-for="(cmd, i) in commands" :key="i">
        <div v-if="cmd.prompt !== false" class="flex gap-2">
          <span class="text-green-400">$</span>
          <span class="text-white">{{ cmd.command }}</span>
        </div>
        <div v-if="cmd.output" class="text-slate-400 pl-4 whitespace-pre-wrap">{{ cmd.output }}</div>
      </div>
      <slot></slot>
    </div>
  </div>
</template>
