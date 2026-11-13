import { Columns3Icon } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cellText } from './data'

let sequence = 0
function gridKey() { sequence += 1; return `result-${sequence}` }

export function ResultGrid(props: { columns: string[]; rows: unknown[][]; caption: string }) {
  return <Grid key={JSON.stringify(props.columns)} {...props} />
}

function Grid({ columns, rows, caption }: { columns: string[]; rows: unknown[][]; caption: string }) {
  const [visible, setVisible] = useState<Set<number>>(() => {
    const selected = columns.flatMap((name, index) => name.toLowerCase() === 'id' ? [] : [index])
    return new Set(selected.length ? selected : columns.map((_name, index) => index))
  })
  const viewColumns = useMemo(() => columns.map((name, index) => ({ name, index, key: gridKey() })), [columns])
  const viewRows = useMemo(() => rows.map(values => ({ values, key: gridKey() })), [rows])
  const shown = viewColumns.filter(column => visible.has(column.index))
  if (!columns.length) return <p className="py-4 text-sm text-muted-foreground">No rows returned.</p>
  return (
    <section className="min-w-0 max-w-full" aria-label={caption}>
      <div className="mb-2 flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>
            <Columns3Icon />Columns ({shown.length}/{columns.length})
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="max-h-80 overflow-y-auto">
            {viewColumns.map(({ name, index, key }) => (
              <DropdownMenuCheckboxItem
                key={key}
                checked={visible.has(index)}
                onCheckedChange={checked => setVisible(current => {
                  const next = new Set(current)
                  if (checked) next.add(index)
                  else next.delete(index)
                  return next
                })}
              >{name}</DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="max-h-[65vh] min-w-0 overflow-auto rounded-md border" tabIndex={0} aria-label="Scrollable query results">
        {shown.length ? (
          <table className="w-max min-w-full border-collapse text-left font-mono text-xs">
            <caption className="sr-only">{caption}</caption>
            <thead className="sticky top-0 z-10 bg-card">
              <tr>{shown.map(column => <th key={column.key} className="h-9 whitespace-nowrap border-b px-3 font-medium">{column.name}</th>)}</tr>
            </thead>
            <tbody>
              {rows.length ? viewRows.map(row => (
                <tr key={row.key} className="border-b last:border-0 hover:bg-muted/40">
                  {shown.map(column => (
                    <td key={column.key} className="h-9 whitespace-nowrap px-3 py-2 align-top">
                      <ResultCell value={row.values[column.index]} />
                    </td>
                  ))}
                </tr>
              )) : <tr><td colSpan={shown.length} className="px-3 py-6 text-center font-sans text-muted-foreground">No rows returned.</td></tr>}
            </tbody>
          </table>
        ) : <p className="p-6 text-sm text-muted-foreground">All columns are hidden. Choose columns to display.</p>}
      </div>
    </section>
  )
}

function ResultCell({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="italic text-muted-foreground" aria-label="Database null value">NULL</span>
  if (value === '') return <span className="italic text-muted-foreground" aria-label="Empty string">Empty string</span>
  const text = cellText(value)
  return <span className="inline-block max-w-[32rem] overflow-hidden text-ellipsis whitespace-nowrap align-top" title={text}>{text}</span>
}
