import { ACCESS_LEVEL_LABEL, ROLE_LABEL } from '@/lib/levels'
import { humanize } from '@/lib/format'

const LABELS: Record<string, string> = {
  first_name: 'First name',
  last_name: 'Last name',
  email: 'Email',
  space_level: 'Space level',
  keyholder_priority: 'Keyholder priority',
  active: 'Active',
  role: 'Role',
  reason: 'Reason',
  result: 'Result',
  status: 'Status',
  mode: 'Mode',
  row_count: 'Rows',
  rows: 'Rows',
  count: 'Count',
  created: 'Created',
  skipped: 'Skipped',
  message: 'Message',
  name: 'Name',
  forgot_to_sign_out: 'Forgot to sign out',
  passed: 'Passed',
  score: 'Score',
  error: 'Error',
  error_class: 'Error type',
  roster: 'Roster records',
  results: 'Results',
  linked: 'Linked people',
  trainings_added: 'Trainings added',
  conflicts: 'Conflicts',
  attempts: 'Attempts',
  duration_ms: 'Milliseconds',
  truncated: 'Result truncated',
  kind: 'Kind',
}
function valueText(key: string, value: unknown): string {
  if (value === null) return 'None'
  if (key === 'space_level' && typeof value === 'number' && value in ACCESS_LEVEL_LABEL)
    return ACCESS_LEVEL_LABEL[value as keyof typeof ACCESS_LEVEL_LABEL]
  if (key === 'role' && typeof value === 'string' && value in ROLE_LABEL)
    return ROLE_LABEL[value as keyof typeof ROLE_LABEL]
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}
/** Deliberately omit internal IDs, hashes, query contents and private tokens. */
export function auditSummary(details: Record<string, unknown>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(details)) {
    if (key === 'fields' && Array.isArray(value)) {
      const fields = value.filter(
        (field): field is string => typeof field === 'string' && field in LABELS,
      )
      if (fields.length) parts.push(`Changed ${fields.map((field) => LABELS[field]).join(', ')}`)
    } else if (
      (key === 'changes' || key === 'changed' || key === 'counts') &&
      value &&
      typeof value === 'object' &&
      !Array.isArray(value)
    ) {
      const nested = auditSummary(value as Record<string, unknown>)
      if (nested) parts.push(nested)
    } else if (key in LABELS) {
      if (
        value &&
        typeof value === 'object' &&
        !Array.isArray(value) &&
        'before' in value &&
        'after' in value
      ) {
        parts.push(
          `${LABELS[key]}: ${valueText(key, value.before)} → ${valueText(key, value.after)}`,
        )
      } else {
        const text = valueText(key, value)
        if (text) parts.push(`${LABELS[key] ?? humanize(key)}: ${text}`)
      }
    }
  }
  return parts.join('; ')
}
