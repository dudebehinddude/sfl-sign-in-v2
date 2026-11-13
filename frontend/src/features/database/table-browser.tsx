import { useQuery } from '@tanstack/react-query'
import { SearchIcon } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Typography } from '@/components/typography'
import { Pager } from '@/components/pager'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { api, isStatus } from '@/lib/api/client'
import { staffKeys } from '@/lib/query-keys'
import type { DatabaseRows, DatabaseTable } from './data'
import { ResultGrid } from './result-grid'

export function TableBrowser({
  principalId,
  tables,
  onEditQuery,
}: {
  principalId: string
  tables: DatabaseTable[]
  onEditQuery: (table: DatabaseTable) => void
}) {
  const [search, setSearch] = useState('')
  const [selection, setSelection] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const selected = tables.find((table) => table.name === selection) ?? tables[0]
  const visible = tables.filter((table) =>
    `${table.schema}.${table.name}`.toLowerCase().includes(search.toLowerCase()),
  )
  if (!selected)
    return (
      <EmptyState
        title="No tables are available"
        description="The restricted read connection does not currently expose any application tables."
      />
    )
  return (
    <div className="grid items-start gap-5 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="flex flex-col gap-3 rounded-lg border p-3" aria-label="Database tables">
        <InputGroup>
          <InputGroupAddon>
            <SearchIcon />
          </InputGroupAddon>
          <InputGroupInput
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Find a table"
            aria-label="Find a database table"
          />
        </InputGroup>
        <div className="flex max-h-96 flex-col gap-1 overflow-auto">
          {visible.length ? (
            visible.map((table) => (
              <Button
                key={`${table.schema}.${table.name}`}
                variant={selected.name === table.name ? 'secondary' : 'ghost'}
                className="justify-start overflow-hidden text-ellipsis"
                aria-pressed={selected.name === table.name}
                title={`${table.schema}.${table.name}`}
                onClick={() => {
                  setSelection(table.name)
                  setPage(1)
                }}
              >
                {table.name}
              </Button>
            ))
          ) : (
            <Typography variant="small">No matching tables.</Typography>
          )}
        </div>
      </aside>
      <section className="flex min-w-0 flex-col gap-4" aria-label={`Rows in ${selected.name}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Typography variant="h3">{selected.name}</Typography>
            <Typography variant="small">Schema {selected.schema}</Typography>
          </div>
          <Button variant="outline" onClick={() => onEditQuery(selected)}>
            Open in SQL editor
          </Button>
        </div>
        <details className="rounded-lg border p-3">
          <summary className="cursor-pointer text-sm font-medium">
            Columns ({selected.columns.length})
          </summary>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            {selected.columns.map((column) => (
              <div key={column.name} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <dt className="text-sm font-medium">{column.name}</dt>
                <dd className="text-xs text-muted-foreground">
                  {column.type}. {column.nullable ? 'Nullable' : 'Required'}
                  {column.primary_key ? ' · Primary key' : ''}
                </dd>
              </div>
            ))}
          </dl>
        </details>
        <TableRows
          key={selected.name}
          principalId={principalId}
          table={selected}
          page={page}
          setPage={setPage}
        />
      </section>
    </div>
  )
}

function TableRows({
  principalId,
  table,
  page,
  setPage,
}: {
  principalId: string
  table: DatabaseTable
  page: number
  setPage: (value: number) => void
}) {
  const [pageSize, setPageSize] = useState(100)
  const query = useQuery({
    queryKey: staffKeys(principalId).topic('database', 'rows', table.name, page, pageSize),
    queryFn: ({ signal }) =>
      api<DatabaseRows>('/api/admin/database/rows', {
        signal,
        query: { table: table.name, page, page_size: pageSize },
      }),
    retry: (count, error) => !isStatus(error, 400, 401, 403, 404, 422, 503) && count < 1,
  })
  if (query.isPending) return <LoadingRows label={`Loading ${table.name}`} />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  const { data } = query
  return (
    <div className="flex flex-col gap-3">
      <ResultGrid
        columns={data.columns}
        rows={data.rows}
        caption={`Rows in public.${table.name}, page ${page}.`}
      />
      {data.truncated ? (
        <Typography variant="small">
          Response limited. Narrow the query to inspect large values.
        </Typography>
      ) : null}
      <Pager page={page} pageSize={pageSize} total={data.total} onPage={setPage} onPageSizeChange={size => { setPageSize(size); setPage(1) }} />
    </div>
  )
}
