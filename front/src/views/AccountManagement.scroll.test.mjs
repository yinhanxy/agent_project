import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./AccountManagement.vue', import.meta.url), 'utf8')

test('desktop account container is height-constrained so it can scroll inside workbench layout', () => {
  const desktopRule = source.match(/@media screen and \(min-width: 901px\)[\s\S]*?\.account-container\s*\{([\s\S]*?)\n  \}/)

  assert.ok(desktopRule, 'desktop account container rule should exist')
  assert.match(desktopRule[1], /height:\s*100%;/)
  assert.match(desktopRule[1], /min-height:\s*0;/)
  assert.match(desktopRule[1], /overflow-y:\s*auto;/)
})
