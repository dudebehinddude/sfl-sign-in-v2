import { useQuery } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'

import { PageHeader } from '@/components/page-header'
import { ErrorState, LoadingRows } from '@/components/query-state'
import { Typography } from '@/components/typography'
import { UserAvatar } from '@/components/user-avatar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { canvasStatusQuery } from '@/features/canvas/api'
import { printingStatusQuery } from '@/features/printing/api'
import { overviewQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { occupancyQuery } from '@/features/occupancy/api'
import { formatDateTime } from '@/lib/format'

export const Route = createFileRoute('/admin/')({
  component: OverviewPage,
})

function OverviewPage() {
  const { keys, user, can } = useStaff()
  const overview = useQuery(overviewQuery(keys))
  const occupancy = useQuery(occupancyQuery)

  return (
    <>
      <PageHeader title="Overview" description="Live state of the lab and its integrations." />

      <Card>
        <CardHeader>
          <CardTitle>
            <Typography variant="h3" as="h2">
              Right now
            </Typography>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {occupancy.isPending ? (
            <LoadingRows rows={1} />
          ) : occupancy.isError ? (
            <ErrorState error={occupancy.error} onRetry={() => occupancy.refetch()} />
          ) : (
            <div className="flex flex-wrap items-center gap-6">
              <div className="flex items-center gap-3">
                <UserAvatar
                  name={occupancy.data.lab.keyholder?.display_name ?? 'No keyholder'}
                  url={occupancy.data.lab.keyholder?.avatar_url}
                  size="lg"
                />
                <div>
                  <Typography variant="small">Keyholder</Typography>
                  <Typography variant="h4" as="p">
                    {occupancy.data.lab.keyholder?.display_name ?? 'Lab closed'}
                  </Typography>
                </div>
              </div>
              <div>
                <Typography variant="small">In the lab</Typography>
                <Typography variant="stat">{occupancy.data.occupants.length}</Typography>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {overview.isPending ? (
        <LoadingRows rows={4} />
      ) : overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => overview.refetch()} />
      ) : (
        <Card size="sm">
          <CardHeader>
            <CardTitle>
              <Typography variant="h3" as="h2">
                Lab records
              </Typography>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-3">
              <Count label="People" value={overview.data.counts.users} />
              <Count label="In the lab" value={overview.data.counts.present} />
              <Count label="Training types" value={overview.data.counts.training_types} />
            </dl>
          </CardContent>
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {user && can('canvas.read') ? <CanvasSummary principalId={user.id} /> : null}
        {user && can('printing.read') ? <PrinterSummary principalId={user.id} /> : null}
      </div>
    </>
  )
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-heading text-2xl tabular-nums">{value}</dd>
    </div>
  )
}
export function CanvasSummary({ principalId }: { principalId: string }) {
  const status = useQuery(canvasStatusQuery(principalId))
  const overview = status.data?.overview
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>
          <Typography variant="h3" as="h2">
            Canvas
          </Typography>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {status.isPending ? (
          <LoadingRows rows={1} />
        ) : status.isError ? (
          <ErrorState error={status.error} onRetry={() => status.refetch()} />
        ) : (
          <>
            <Typography>{overview ? { idle: 'Ready', running: 'Syncing', error: 'Last sync failed', unconfigured: 'Not configured' }[overview.status] : 'Unavailable'}</Typography>
            <Typography variant="small">
              Last successful sync: {overview?.last_success_at ? formatDateTime(overview.last_success_at) : overview ? 'Never' : 'Unavailable'}
            </Typography>
            {overview?.status === 'error' && overview.last_error ? <Typography variant="small">{overview.last_error}</Typography> : null}
          </>
        )}
        <Link to="/admin/canvas" className="text-sm underline underline-offset-4">
          Open Canvas sync
        </Link>
      </CardContent>
    </Card>
  )
}
function PrinterSummary({ principalId }: { principalId: string }) {
  const status = useQuery(printingStatusQuery(principalId))
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>
          <Typography variant="h3" as="h2">
            Label printer
          </Typography>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {status.isPending ? (
          <LoadingRows rows={1} />
        ) : status.isError ? (
          <ErrorState error={status.error} onRetry={() => status.refetch()} />
        ) : (
          <>
            <Typography>
              {status.data.connected ? (status.data.busy ? 'Printing' : 'Connected') : 'Offline'}
            </Typography>
            <Typography variant="small">
              {status.data.last_result
                ? `Last result: ${status.data.last_result.status}, ${formatDateTime(status.data.last_result.at)}.`
                : 'No result received since this server started.'}
            </Typography>
          </>
        )}
        <Link to="/admin/printing" className="text-sm underline underline-offset-4">
          Open label printing
        </Link>
      </CardContent>
    </Card>
  )
}
