import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Pager } from '@/components/pager'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Typography } from '@/components/typography'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { canvasPeopleQuery } from './api'
import type { CanvasBinding } from './types'

export function CanvasPeopleList({ principalId, canReadUsers }: {
  principalId: string
  canReadUsers: boolean
}) {
  const [binding, setBinding] = useState<CanvasBinding>('unmatched')
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const people = useQuery(canvasPeopleQuery(principalId, {
    binding, search, page, page_size: pageSize,
  }))
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-labelledby="canvas-people">
      <Typography variant="h2" id="canvas-people">Canvas Users</Typography>
      <form className="flex flex-wrap items-end gap-3" onSubmit={event => {
        event.preventDefault()
        setSearch(draft.trim())
        setPage(1)
      }}>
        <label className="flex flex-col gap-2 text-sm">
          Binding
          <NativeSelect value={binding} onChange={event => {
            setBinding(event.target.value as CanvasBinding)
            setPage(1)
          }}>
            <NativeSelectOption value="unmatched">Unmatched</NativeSelectOption>
            <NativeSelectOption value="conflicts">Conflicts</NativeSelectOption>
            <NativeSelectOption value="all">All cached people</NativeSelectOption>
          </NativeSelect>
        </label>
        <label className="flex min-w-0 flex-1 flex-col gap-2 text-sm sm:min-w-64">
          Search name or email
          <Input value={draft} onChange={event => setDraft(event.target.value)} maxLength={200} />
        </label>
        <Button type="submit">Search</Button>
      </form>
      <Typography variant="muted">
        {binding === 'conflicts'
          ? 'Conflicting identity ownership needs administrator review.'
          : binding === 'unmatched'
            ? 'Cached people may remain unmatched until their first registration.'
            : 'All cached Canvas people, including linked and unmatched records.'}
      </Typography>
      {people.isPending ? <LoadingRows label="Loading Canvas people" /> : people.isError ? (
        <ErrorState error={people.error} onRetry={() => people.refetch()} />
      ) : (
        <>
          {!people.data.items.length ? <EmptyState title="No matching Canvas people" /> : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Name</TableHead><TableHead>Source email</TableHead>
                <TableHead>Canvas ID</TableHead><TableHead>Binding</TableHead>
              </TableRow></TableHeader>
              <TableBody>{people.data.items.map(person => (
                <TableRow key={person.id}>
                  <TableCell>{person.user_id && canReadUsers ? (
                    <Link to="/admin/users/$userId" params={{ userId: person.user_id }} className="underline underline-offset-4">
                      {person.display_name || 'Name unavailable'}
                    </Link>
                  ) : person.display_name || 'Name unavailable'}</TableCell>
                  <TableCell>{person.email ?? 'Not supplied by Canvas'}</TableCell>
                  <TableCell>{person.canvas_id}</TableCell>
                  <TableCell className="max-w-lg whitespace-normal">
                    {person.conflict ?? (person.user_id ? 'Linked' : 'Not linked')}
                  </TableCell>
                </TableRow>
              ))}</TableBody>
            </Table>
          )}
          <Pager page={people.data.page} pageSize={people.data.page_size} total={people.data.total}
            onPage={setPage} onPageSizeChange={size => { setPageSize(size); setPage(1) }} />
        </>
      )}
    </section>
  )
}
