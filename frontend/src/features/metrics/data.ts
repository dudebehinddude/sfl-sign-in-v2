import { buildUrl } from '@/lib/api/client'

export interface MetricsFilters {
  start: string
  end: string
}
export interface DailyMetrics {
  date: string
  visits: number
  unique_visitors: number
  total_hours: number
}
export interface MetricsResponse extends MetricsFilters {
  timezone: string
  summary: {
    unique_visitors: number
    visits: number
    finalized_visits: number
    total_hours: number
    average_visit_minutes: number
    new_visitors: number
    excluded_visits: number
    open_visits: number
  }
  daily: DailyMetrics[]
  definitions: Record<string, string>
}

function calendarTimestamp(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const timestamp = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value
    ? timestamp
    : null
}

export function validateMetricsFilters(filters: MetricsFilters): string | null {
  const start = calendarTimestamp(filters.start)
  const end = calendarTimestamp(filters.end)
  if (start === null || end === null) return 'Choose valid start and end dates.'
  if (end < start) return 'End date cannot be before the start date.'
  if ((end - start) / 86_400_000 + 1 > 1830) return 'Choose a date range no longer than five years.'
  return null
}

/** Calendar arithmetic keeps the inclusive UI independent of DST-length days. */
function shiftDate(value: string, days: number): string {
  return new Date(calendarTimestamp(value)! + days * 86_400_000).toISOString().slice(0, 10)
}

export function previousCalendarMonth(now = new Date(Date.now())): MetricsFilters {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: 'numeric' }).formatToParts(now)
  const year = Number(parts.find(part => part.type === 'year')!.value)
  const month = Number(parts.find(part => part.type === 'month')!.value)
  return {
    start: new Date(Date.UTC(year, month - 2, 1)).toISOString().slice(0, 10),
    end: new Date(Date.UTC(year, month - 1, 0)).toISOString().slice(0, 10),
  }
}

export function metricsQueryParams(filters: MetricsFilters) {
  return { start: filters.start, end: shiftDate(filters.end, 1), timezone: 'America/New_York' }
}

export function metricsCsvUrl(filters: MetricsFilters): string {
  return buildUrl('/api/admin/metrics.csv', metricsQueryParams(filters))
}

export function filtersFromResponse(data: MetricsResponse): MetricsFilters {
  return { start: data.start, end: shiftDate(data.end, -1) }
}
