import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCwIcon } from 'lucide-react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Typography } from '@/components/typography'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { useSession } from '@/features/auth/session'
import { formatDateTime } from '@/lib/format'
import { staffKeys } from '@/lib/query-keys'
import { canvasStatusQuery, requestCanvasSync } from './api'
import { CanvasPeopleList } from './people'

export function CanvasPage() {
  const { user, can } = useSession()
  if (!user || !can('canvas.read')) return <EmptyState title="Canvas access required" />
  return <CanvasControls key={user.id} principalId={user.id} canWrite={can('canvas.write')} canReadUsers={can('users.read')} />
}
function CanvasControls({ principalId, canWrite, canReadUsers }: {
  principalId: string
  canWrite: boolean
  canReadUsers: boolean
}) {
  const client = useQueryClient()
  const status = useQuery(canvasStatusQuery(principalId))
  const sync = useMutation({
    mutationFn: () => requestCanvasSync(),
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: staffKeys(principalId).topic('canvas') })
    },
  })
  const overview = status.data?.overview
  const running = overview?.status === 'running'
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <Typography variant="h1">Canvas sync</Typography>
        {canWrite ? <Button disabled={!status.data?.configured || !overview || sync.isPending || running}
          onClick={() => sync.mutate()}><RefreshCwIcon />{running ? 'Syncing…' : 'Sync Canvas'}</Button> : null}
      </header>
      {status.isPending ? <LoadingRows label="Loading Canvas state" /> : status.isError ? (
        <ErrorState error={status.error} onRetry={() => status.refetch()} />
      ) : (
        <>
          <div className="text-sm">
            <span className="text-muted-foreground">Last successful sync: </span>
            {overview?.last_success_at ? <time dateTime={overview.last_success_at}>{formatDateTime(overview.last_success_at)}</time> : overview ? 'Never' : 'Unavailable'}
          </div>
          {!status.data.configured ? <Alert>
            <AlertTitle>Canvas is not configured</AlertTitle>
            <AlertDescription>{status.data.setup_message ?? 'Set the Canvas course and API token in the server environment.'}</AlertDescription>
          </Alert> : null}
          {overview?.status === 'error' && overview.last_error ? <Alert variant="destructive">
            <AlertTitle>Last sync failed</AlertTitle><AlertDescription>{overview.last_error}</AlertDescription>
          </Alert> : null}
        </>
      )}
      {sync.data && !running ? <p role="status" className="text-sm text-muted-foreground">{sync.data.message}</p> : null}
      {sync.isError ? <ErrorState error={sync.error} title="Sync could not start" /> : null}
      <CanvasPeopleList principalId={principalId} canReadUsers={canReadUsers} />
    </div>
  )
}
