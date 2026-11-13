const timeFormat = new Intl.DateTimeFormat(undefined, {
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'America/New_York',
})
const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'America/New_York',
})
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' })
const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })

export function formatTime(iso: string | null | undefined): string {
  return iso ? timeFormat.format(new Date(iso)) : '—'
}

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTimeFormat.format(new Date(iso)) : '—'
}

/** Formats a calendar date (YYYY-MM-DD) without shifting it through the local timezone. */
export function formatCalendarDate(date: string): string {
  return dateFormat.format(new Date(`${date}T00:00:00Z`))
}

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : numberFormat.format(value)
}

export function formatMinutes(totalMinutes: number): string {
  const minutes = Math.max(0, Math.round(totalMinutes))
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (!hours) return `${rest} min`
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

export function formatDuration(startIso: string, endIso: string | null): string {
  if (!endIso) return 'Still here'
  return formatMinutes((new Date(endIso).getTime() - new Date(startIso).getTime()) / 60_000)
}

export function humanize(key: string): string {
  const text = key.replace(/[_-]+/g, ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}
