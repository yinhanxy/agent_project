import test from 'node:test'
import assert from 'node:assert/strict'
import { buildDepartmentSummaries } from './departmentSummary.js'

test('builds department summaries with members and role counts', () => {
  const departments = [
    { dept_id: 1, name: '研发部' },
    { dept_id: 2, name: '运营部' },
  ]
  const users = [
    { uuid: 'u1', username: 'Alice', email: 'a@example.com', dept_id: 1, is_dept_admin: true, is_admin: false },
    { uuid: 'u2', username: 'Bob', email: 'b@example.com', dept_id: 1, is_dept_admin: false, is_admin: false },
    { uuid: 'u3', username: 'Cara', email: 'c@example.com', dept_id: 2, is_dept_admin: false, is_admin: true },
    { uuid: 'u4', username: 'Dana', email: 'd@example.com', dept_id: null, is_dept_admin: false, is_admin: false },
  ]

  assert.deepEqual(buildDepartmentSummaries(departments, users), [
    {
      dept_id: 1,
      name: '研发部',
      members: [users[0], users[1]],
      memberCount: 2,
      deptAdminCount: 1,
      normalMemberCount: 1,
    },
    {
      dept_id: 2,
      name: '运营部',
      members: [users[2]],
      memberCount: 1,
      deptAdminCount: 0,
      normalMemberCount: 1,
    },
  ])
})
