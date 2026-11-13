import { expect, it } from 'vitest'
import { auditSummary } from './audit-details'
it('turns domain changes into human labels and omits internal identifiers and sensitive metadata', () => {
  const summary = auditSummary({
    fields: ['first_name', 'active', 'password_hash'],
    space_level: { before: 0, after: 1 },
    role: 'admin',
    active: false,
    reason: 'Corrected duplicate award',
    user_id: 'private-id',
    sql: 'secret SQL',
    query_hash: 'secret digest',
    token_hash: 'secret token',
  })
  expect(summary).toContain('Changed First name, Active')
  expect(summary).toContain('Space level: Member → Volunteer')
  expect(summary).toContain('Role: Admin')
  expect(summary).toContain('Active: No')
  expect(summary).toContain('Corrected duplicate award')
  expect(summary).not.toMatch(/private-id|secret|password_hash|user_id/)
})
