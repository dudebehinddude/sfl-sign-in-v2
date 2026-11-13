import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PrinterIcon } from 'lucide-react'
import { useDeferredValue, useState } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Typography } from '@/components/typography'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useSession } from '@/features/auth/session'
import { formatDateTime } from '@/lib/format'
import { staffKeys } from '@/lib/query-keys'
import { printingStatusQuery, printPeopleQuery, printUserLabel } from './api'

export function PrintingPage() {
  const { user, can } = useSession()
  if (!user || !can('printing.read')) return <EmptyState title="Printing access required" />
  return (
    <PrinterControls
      key={user.id}
      principalId={user.id}
      canPrint={can('printing.write') && can('users.read')}
    />
  )
}
function PrinterControls({ principalId, canPrint }: { principalId: string; canPrint: boolean }) {
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search.trim())
  const client = useQueryClient()
  const status = useQuery(printingStatusQuery(principalId))
  const people = useQuery({
    ...printPeopleQuery(principalId, deferredSearch),
    enabled: canPrint && deferredSearch.length >= 2,
  })
  const print = useMutation({
    mutationFn: printUserLabel,
    retry: false,
    onSettled: () => {
      void client.invalidateQueries({ queryKey: staffKeys(principalId).topic('printing') })
    },
  })
  const last = status.data?.last_result
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <header>
        <Typography variant="h1">Label printing</Typography>
        <Typography variant="muted">Labels go straight to the connected kiosk printer.</Typography>
      </header>
      {status.isPending ? (
        <LoadingRows rows={2} label="Checking printer" />
      ) : status.isError ? (
        <ErrorState error={status.error} onRetry={() => status.refetch()} />
      ) : (
        <section
          className="flex flex-col gap-4 rounded-lg border p-5"
          aria-labelledby="printer-status"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Typography variant="h2" id="printer-status">
              Printer status
            </Typography>
            <Badge variant={status.data.connected ? 'secondary' : 'outline'}>
              {status.data.connected ? (status.data.busy ? 'Printing' : 'Connected') : 'Offline'}
            </Badge>
          </div>
          <Typography>
            When the printer is offline or busy, the label is dropped. Connecting later does not
            print old labels.
          </Typography>
          {last ? (
            <div className="flex flex-col gap-1">
              <Typography variant="h3">
                Last result:{' '}
                {last.status === 'printed'
                  ? 'Printed'
                  : last.status === 'failed'
                    ? 'Failed'
                    : 'Unknown'}
              </Typography>
              <Typography>
                {last.display_name} · {formatDateTime(last.at)}
              </Typography>
              {last.message ? <Typography variant="muted">{last.message}</Typography> : null}
              {last.status === 'unknown' ? (
                <Typography variant="small">
                  Check whether a label came out before printing another.
                </Typography>
              ) : null}
            </div>
          ) : (
            <Typography variant="muted">No result received since this server started.</Typography>
          )}
          <Button
            variant="outline"
            className="self-start"
            disabled={status.isFetching}
            onClick={() => status.refetch()}
          >
            Refresh status
          </Button>
        </section>
      )}
      {print.data ? (
        <Alert role="status" variant={print.data.status === 'sent' ? 'default' : 'destructive'}>
          <PrinterIcon />
          <AlertTitle>
            {print.data.status === 'sent'
              ? 'Label sent'
              : print.data.status === 'busy'
                ? 'Printer busy'
                : 'Printer offline'}
          </AlertTitle>
          <AlertDescription>
            {print.data.message}
            {print.data.status === 'sent'
              ? ' Sending is not confirmation that the label printed.'
              : ''}
          </AlertDescription>
        </Alert>
      ) : null}
      {print.isError ? (
        <ErrorState
          error={print.error}
          title="Print result uncertain — check the printer before sending another label"
        />
      ) : null}
      {canPrint ? (
        <section
          className="flex flex-col gap-3 rounded-lg border p-5"
          aria-labelledby="print-person"
        >
          <Typography variant="h2" id="print-person">
            Print a label
          </Typography>
          <Label htmlFor="print-person-search">Find a person</Label>
          <Input
            id="print-person-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name or email (at least two characters)"
            autoComplete="off"
          />
          <Typography variant="small">
            Uses their current name and badges. You can use your own label to test the printer.
          </Typography>
          {deferredSearch.length >= 2 ? (
            people.isPending ? (
              <LoadingRows rows={2} />
            ) : people.isError ? (
              <ErrorState error={people.error} onRetry={() => people.refetch()} />
            ) : people.data?.items.length ? (
              <ul className="divide-y">
                {people.data.items.map((person) => (
                  <li
                    key={person.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-3"
                  >
                    <div className="min-w-0">
                      <Typography className="break-words">{person.display_name}</Typography>
                      <Typography variant="small" className="break-all">
                        {person.email ?? 'No email recorded'}
                      </Typography>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={
                        print.isPending ||
                        !person.active ||
                        !status.data?.connected ||
                        status.data.busy
                      }
                      onClick={() => print.mutate(person.id)}
                    >
                      <PrinterIcon />
                      Print label
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <Typography variant="muted">No matching people.</Typography>
            )
          ) : null}
          {people.data && people.data.total > people.data.items.length ? (
            <Typography variant="small">
              Showing the first {people.data.items.length} matches. Narrow the search to find
              someone else.
            </Typography>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
