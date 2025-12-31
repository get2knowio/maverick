import { defineConfig } from 'unocss'

export default defineConfig({
  // Safelist g2k theme utility classes
  safelist: [
    // Brand colors
    'text-brass', 'bg-brass', 'border-brass',
    'text-teal', 'bg-teal', 'border-teal',
    'text-coral', 'bg-coral', 'border-coral',
    // Surface utilities
    'bg-base', 'bg-raised', 'bg-sunken',
    // Text utilities
    'text-primary', 'text-secondary', 'text-muted',
    // Status colors
    'status-success', 'status-warning', 'status-error', 'status-info',
    // Component classes
    'g2k-surface', 'g2k-tagline-pill', 'g2k-float',
    'feature-card', 'principle-card', 'arch-box', 'agent-badge', 'stage', 'terminal',
    // Arch-box variants
    'arch-box cli', 'arch-box workflow', 'arch-box agent', 'arch-box tool',
    // Agent badge variants
    'agent-badge implementer', 'agent-badge reviewer', 'agent-badge fixer', 'agent-badge generator',
    // Stage variants
    'stage pending', 'stage active', 'stage complete', 'stage failed',
    // Principle card variants
    'principle-card teal', 'principle-card coral',
    // Terminal parts
    'terminal-header', 'terminal-body', 'terminal-dot',
    'terminal-dot red', 'terminal-dot yellow', 'terminal-dot green',
  ],

  // Theme configuration to extend with g2k colors
  theme: {
    colors: {
      // Map g2k colors for UnoCSS utilities (approximations for direct use)
      'g2k-brass': 'hsl(46 70% 47%)',
      'g2k-brass-shine': 'hsl(49 75% 59%)',
      'g2k-teal': 'hsl(180 49% 33%)',
      'g2k-teal-oxidized': 'hsl(181 33% 50%)',
      'g2k-coral': 'hsl(14 67% 63%)',
      'g2k-copper': 'hsl(29 55% 46%)',
      'g2k-success': 'hsl(153 42% 30%)',
      'g2k-warning': 'hsl(30 65% 44%)',
      'g2k-error': 'hsl(358 65% 37%)',
      'g2k-info': 'hsl(213 64% 33%)',
    },
  },

  // Shortcuts for common patterns
  shortcuts: {
    'g2k-gradient-text': 'bg-gradient-to-r from-[hsl(46,70%,47%)] via-[hsl(49,75%,59%)] to-[hsl(46,70%,47%)] bg-clip-text text-transparent',
  },
})
