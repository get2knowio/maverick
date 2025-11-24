// tasks/markdown.mjs
import fs from 'fs/promises'
import path from 'path'

/**
 * Parse a tasks.md file into phase objects with task metadata.
 * @param {string} tasksFile - Path to tasks.md file
 * @param {string} baseDir - Base directory for resolving relative paths
 * @returns {Promise<Array>} Array of phase objects
 */
export async function parsePhases(tasksFile, baseDir) {
  const fullPath = path.isAbsolute(tasksFile)
    ? tasksFile
    : path.join(baseDir, tasksFile)

  const raw = await fs.readFile(fullPath, 'utf8')
  const lines = raw.split(/\r?\n/)

  const phases = []
  let current = null

  for (const line of lines) {
    const trimmed = line.trim()
    const m = /^##\s+Phase\s+([^:]+):(.*)$/.exec(trimmed)
    if (m) {
      if (current) {
        current.bodyText = current.body.join('\n').trim()
        current.tasks = extractTasks(current.body)
        current.totalTasks = current.tasks.length
        current.outstandingTasks = countOutstandingTasks(current.tasks)
        phases.push(current)
      }
      current = {
        identifier: m[1].trim(),
        title: m[2].trim(),
        body: []
      }
      continue
    }

    if (current) current.body.push(line)
  }

  if (current) {
    current.bodyText = current.body.join('\n').trim()
    current.tasks = extractTasks(current.body)
    current.totalTasks = current.tasks.length
    current.outstandingTasks = countOutstandingTasks(current.tasks)
    phases.push(current)
  }

  return phases
}

/**
 * Check if a file exists.
 * @param {string} filePath - Path to check
 * @returns {Promise<boolean>}
 */
export async function fileExists(filePath) {
  try {
    await fs.access(filePath)
    return true
  } catch {
    return false
  }
}

/**
 * Extract task lines from phase body.
 * @param {string[]} lines - Body lines
 * @returns {string[]} Task lines
 */
function extractTasks(lines) {
  return lines
    .map(l => l.trim())
    .filter(l => l.startsWith('- ['))
}

/**
 * Count outstanding (uncompleted) tasks.
 * @param {string[]} tasks - Task lines
 * @returns {number} Count of outstanding tasks
 */
function countOutstandingTasks(tasks) {
  // A task is considered completed if it starts with "- [x]" or "- [X]"
  // Anything else (e.g., "- [ ]") is outstanding.
  let outstanding = 0
  for (const t of tasks) {
    const completed = /^- \[[xX]\]/.test(t)
    if (!completed) outstanding += 1
  }
  return outstanding
}
