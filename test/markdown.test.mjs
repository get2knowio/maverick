import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { fileExists, parsePhases } from '../src/tasks/markdown.mjs'

const fixturesDir = path.join(process.cwd(), 'test', 'fixtures')

test('parsePhases extracts identifiers, titles, and task counts', async () => {
  const phases = await parsePhases('tasks.md', fixturesDir)

  assert.equal(phases.length, 2)

  const [first, second] = phases

  assert.equal(first.identifier, '001')
  assert.equal(first.title, 'Setup')
  assert.equal(first.totalTasks, 3)
  assert.equal(first.outstandingTasks, 1)
  assert.match(first.bodyText, /initialize repository/)

  assert.equal(second.identifier, '002')
  assert.equal(second.title, 'Build')
  assert.equal(second.totalTasks, 2)
  assert.equal(second.outstandingTasks, 2)
})

test('fileExists returns true when the file is present and false otherwise', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'maverick-test-'))
  const filePath = path.join(dir, 'exists.txt')
  await fs.writeFile(filePath, 'hi')

  assert.equal(await fileExists(filePath), true)
  assert.equal(await fileExists(path.join(dir, 'missing.txt')), false)
})

test('parsePhases throws a helpful error when the tasks file is missing', async () => {
  const missingPath = path.join(fixturesDir, 'missing-tasks.md')

  await assert.rejects(
    () => parsePhases(missingPath, fixturesDir),
    err => {
      assert.equal(err.code, 'TASKS_FILE_NOT_FOUND')
      assert.ok(err.message.includes(missingPath))
      assert.match(err.message, /Tasks file not found/)
      return true
    }
  )
})
