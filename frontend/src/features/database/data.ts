export interface DatabaseColumn {
  name: string
  type: string
  nullable: boolean
  primary_key: boolean
}
export interface DatabaseTable {
  schema: string
  name: string
  columns: DatabaseColumn[]
}
export interface DatabaseCatalog {
  tables: DatabaseTable[]
}
export interface DatabaseRows {
  columns: string[]
  rows: unknown[][]
  total: number
  page: number
  page_size: number
  truncated: boolean
}
export interface SqlRequest {
  sql: string
}
export interface SqlResult {
  columns: string[]
  rows: unknown[][]
  row_count: number
  truncated: boolean
  duration_ms: number
  transaction_status: 'read_only' | 'preview' | 'committed' | 'rolled_back'
  preview_id?: string
  expires_at?: string
  table?: string
  operation?: string
  changes?: { before: Record<string, unknown> | null; after: Record<string, unknown> | null }[]
}

function quote(value: string) {
  return `"${value.replaceAll('"', '""')}"`
}

export function sqlForTable(table: DatabaseTable): string {
  const projection = table.columns.map(column => quote(column.name)).join(', ') || '*'
  return `SELECT ${projection} FROM ${quote(table.schema)}.${quote(table.name)} LIMIT 100;`
}

export function cellText(value: unknown): string {
  if (value === null || value === undefined) return 'NULL'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function field(value: unknown): string {
  let text = cellText(value)
  // A spreadsheet must not execute a query's text values or column aliases.
  // Native negative numbers remain numbers; string values get protected.
  if (typeof value === 'string' && (/^\s*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text)))
    text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

export function resultCsv(columns: string[], rows: unknown[][]): string {
  return (
    [columns.map(field), ...rows.map((row) => row.map(field))]
      .map((row) => row.join(','))
      .join('\r\n') + '\r\n'
  )
}

export function downloadResult(columns: string[], rows: unknown[][]) {
  const url = URL.createObjectURL(
    new Blob([resultCsv(columns, rows)], { type: 'text/csv;charset=utf-8' }),
  )
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `sfl-query-${new Date().toISOString().replaceAll(':', '-')}.csv`
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
