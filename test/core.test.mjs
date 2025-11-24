import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { executeStep, makeStep, runAndCapture } from '../src/steps/core.mjs'

test('runAndCapture returns stdout/stderr and tees stdout to a file', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'maverick-step-'))
  const tee = path.join(dir, 'tee.txt')

  const { stdout, stderr } = await runAndCapture(process.execPath, ['-e', 'console.log("hello"); console.error("warn")'], { teeToFile: tee })

  assert.match(stdout, /hello/)
  assert.match(stderr, /warn/)
  const written = await fs.readFile(tee, 'utf8')
  assert.match(written, /hello/)
})

test('executeStep honors captureTo through makeStep descriptors', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'maverick-step-'))
  const capturePath = path.join(dir, 'captured.txt')

  const step = makeStep({
    id: 'echo-step',
    kind: 'cmd',
    cmd: process.execPath,
    args: ['-e', 'console.log("step ran")'],
    captureTo: capturePath,
  })

  const result = await executeStep(step, { logger: () => {}, verbose: true })

  assert.match(result.stdout, /step ran/)
  const captured = await fs.readFile(capturePath, 'utf8')
  assert.match(captured, /step ran/)
})
