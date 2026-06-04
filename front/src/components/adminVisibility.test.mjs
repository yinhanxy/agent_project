import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const adminEntryFiles = [
  new URL('./DesktopRail.vue', import.meta.url),
  new URL('./TabBar.vue', import.meta.url),
  new URL('../views/AIChat.vue', import.meta.url),
  new URL('../views/My.vue', import.meta.url),
]

test('admin entry points use the unified super-admin getter', () => {
  for (const file of adminEntryFiles) {
    const source = readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /userStore\.isAdmin/)
    assert.match(source, /userStore\.isSuperAdmin/)
  }
})
