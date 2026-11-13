import { describe, expect, it } from 'vitest'
import { cellText, resultCsv, sqlForTable } from './data'

describe('database result handling', () => {
  it('quotes catalog identifiers rather than interpolating SQL syntax', () => {
    expect(sqlForTable({ schema: 'public', name: 'some"table', columns: [] })).toBe(
      'SELECT * FROM "public"."some""table" LIMIT 100;',
    )
  })
  it('builds SQL from the visible catalog columns', () => {
    expect(sqlForTable({ schema: 'public', name: 'users', columns: [
      { name: 'id', type: 'uuid', nullable: false, primary_key: true },
      { name: 'first_name', type: 'text', nullable: false, primary_key: false },
    ] })).toBe('SELECT "id", "first_name" FROM "public"."users" LIMIT 100;')
  })
  it('protects string values and headers against spreadsheet formulas', () => {
    const csv = resultCsv(
      ['=unsafe', 'value'],
      [
        ['  =1+1', 'a,"b"\nline'],
        [-3, null],
        ['', true],
      ],
    )
    expect(csv).toContain('"\'=unsafe"')
    expect(csv).toContain('"\'  =1+1"')
    expect(csv).toContain('"a,""b""\nline"')
    expect(csv).toContain('"-3","NULL"')
    expect(csv).toContain('"","true"')
  })
  it('retains null versus empty-string information for display', () => {
    expect(cellText(null)).toBe('NULL')
    expect(cellText('')).toBe('')
    expect(cellText({ count: 2 })).toBe('{"count":2}')
  })
})
