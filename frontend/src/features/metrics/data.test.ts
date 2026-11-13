import { describe, expect, it } from 'vitest'
import { filtersFromResponse, metricsCsvUrl, metricsQueryParams, previousCalendarMonth, validateMetricsFilters, type MetricsResponse } from './data'

describe('inclusive Eastern reporting filters', () => {
  it('accepts a single day, rejects invalid dates and reversed/too-long ranges', () => {
    expect(validateMetricsFilters({ start: '2026-02-30', end: '2026-03-02' })).toMatch(/valid start/)
    expect(validateMetricsFilters({ start: '2026-03-08', end: '2026-03-08' })).toBeNull()
    expect(validateMetricsFilters({ start: '2026-03-09', end: '2026-03-08' })).toMatch(/before/)
    expect(validateMetricsFilters({ start: '2020-01-01', end: '2026-01-01' })).toMatch(/five years/)
  })
  it('uses the previous complete calendar month, including leap years and Eastern month boundaries', () => {
    expect(previousCalendarMonth(new Date('2026-11-09T17:00:00Z'))).toEqual({ start: '2026-10-01', end: '2026-10-31' })
    expect(previousCalendarMonth(new Date('2024-03-15T17:00:00Z'))).toEqual({ start: '2024-02-01', end: '2024-02-29' })
    expect(previousCalendarMonth(new Date('2026-01-09T17:00:00Z'))).toEqual({ start: '2025-12-01', end: '2025-12-31' })
    expect(previousCalendarMonth(new Date('2026-03-01T02:00:00Z'))).toEqual({ start: '2026-01-01', end: '2026-01-31' })
  })
  it('converts inclusive dates once for JSON and CSV, including DST transition days', () => {
    const filters = { start: '2026-11-01', end: '2026-11-01' }
    const expected = { start: '2026-11-01', end: '2026-11-02', timezone: 'America/New_York' }
    expect(metricsQueryParams(filters)).toEqual(expected)
    const url = metricsCsvUrl(filters)
    expect(url.startsWith('/api/admin/metrics.csv?')).toBe(true)
    expect(Object.fromEntries(new URLSearchParams(url.split('?')[1]))).toEqual(expected)
    expect(filtersFromResponse({ ...expected } as MetricsResponse)).toEqual(filters)
  })
})
