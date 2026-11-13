import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { DownloadIcon, RefreshCwIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Typography } from '@/components/typography'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useSession } from '@/features/auth/session'
import { ApiError, api, isStatus } from '@/lib/api/client'
import { formatCalendarDate, formatMinutes, formatNumber } from '@/lib/format'
import { staffKeys } from '@/lib/query-keys'
import { DailyCharts } from './daily-charts'
import { DailyTable } from './daily-table'
import {
  filtersFromResponse,
  metricsQueryParams,
  previousCalendarMonth,
  metricsCsvUrl,
  validateMetricsFilters,
  type MetricsFilters,
  type MetricsResponse,
} from './data'

export function MetricsPage() {
  const { query, user, can } = useSession()
  if (query.isPending) return <LoadingRows label="Checking reporting permissions" />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  if (!user || !can('metrics.read'))
    return (
      <ErrorState
        error={new ApiError(403, null, 'You need reporting permission to view lab metrics.')}
      />
    )
  return <MetricsDashboard key={user.id} principalId={user.id} />
}

function MetricsDashboard({ principalId }: { principalId: string }) {
  const [filters, setFilters] = useState<MetricsFilters>(previousCalendarMonth)
  const [draft, setDraft] = useState<MetricsFilters | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const metrics = useQuery({
    queryKey: staffKeys(principalId).topic('metrics', filters),
    queryFn: ({ signal }) =>
      api<MetricsResponse>('/api/admin/metrics', {
        signal,
        query: metricsQueryParams(filters),
      }),
    placeholderData: keepPreviousData,
    retry: (count, error) => !isStatus(error, 400, 401, 403, 422) && count < 1,
  })
  const data = metrics.data
  const form = draft ?? filters
  function apply(event: FormEvent) {
    event.preventDefault()
    const error = validateMetricsFilters(form)
    setValidationError(error)
    if (!error) setFilters({ ...form })
  }
  const summary = data?.summary
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Typography variant="h1">Lab metrics</Typography>
          <Typography variant="muted">
            Attendance, finalized time, and first-time visitors.
          </Typography>
        </div>
        {data ? (
          <a
            className={buttonVariants({ variant: 'outline' })}
            href={metricsCsvUrl(filtersFromResponse(data))}
          >
            <DownloadIcon />
            Export CSV
          </a>
        ) : null}
      </header>
      <form
        className="flex flex-wrap items-end gap-3 rounded-lg border p-4"
        onSubmit={apply}
        aria-label="Reporting filters"
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor="metrics-start">Start date</Label>
          <Input
            id="metrics-start"
            type="date"
            value={form.start}
            required
            disabled={!data || metrics.isFetching}
            onChange={(event) => setDraft({ ...form, start: event.target.value })}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="metrics-end">End date</Label>
          <Input
            id="metrics-end"
            type="date"
            value={form.end}
            required
            disabled={!data || metrics.isFetching}
            onChange={(event) => setDraft({ ...form, end: event.target.value })}
          />
        </div>
        <Button type="submit" disabled={!data || metrics.isFetching}>
          Apply dates
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={metrics.isFetching}
          onClick={() => metrics.refetch()}
          aria-label="Refresh metrics"
        >
          <RefreshCwIcon
            className={metrics.isFetching ? 'animate-spin motion-reduce:animate-none' : undefined}
          />
        </Button>

      </form>
      {validationError ? (
        <Alert variant="destructive">
          <AlertTitle>Check the reporting range</AlertTitle>
          <AlertDescription>{validationError}</AlertDescription>
        </Alert>
      ) : null}
      {metrics.isError ? (
        <ErrorState error={metrics.error} onRetry={() => metrics.refetch()} />
      ) : null}
      {metrics.isPending ? (
        <LoadingRows rows={6} label="Loading lab metrics" />
      ) : data && summary ? (
        <>
          <Typography variant="small" role="status" aria-live="polite">
            Showing {formatCalendarDate(data.start)} through {formatCalendarDate(filtersFromResponse(data).end)}.
            {metrics.isFetching ? '. Updating' : ''}
          </Typography>
          <dl className="grid gap-x-6 gap-y-5 rounded-lg border p-5 sm:grid-cols-2 xl:grid-cols-3">
            <Metric
              label="Unique visitors"
              value={summary.unique_visitors.toLocaleString()}
              detail="Distinct people with any visit in the range."
            />
            <Metric
              label="Visits"
              value={summary.visits.toLocaleString()}
              detail="All visits, including open visits and forgotten sign-outs."
            />
            <Metric
              label="First-time visitors"
              value={summary.new_visitors.toLocaleString()}
              detail="Their first-ever visit started in this range."
            />
            <Metric
              label="Finalized person-hours"
              value={formatNumber(summary.total_hours)}
              detail="Completed time inside the selected range, excluding forgotten sign-outs."
            />
            <Metric
              label="Average finalized stay"
              value={formatMinutes(summary.average_visit_minutes)}
              detail={`Calculated across ${summary.finalized_visits.toLocaleString()} finalized visits.`}
            />
            <Metric
              label="Finalized visits"
              value={summary.finalized_visits.toLocaleString()}
              detail="Closed visits without forgotten sign-outs."
            />
          </dl>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{summary.open_visits.toLocaleString()} open visits</Badge>
            <Badge variant="outline">
              {summary.excluded_visits.toLocaleString()} other excluded visits
            </Badge>
            <Typography variant="small">
              Open visits and forgotten sign-outs are excluded from finalized hours and averages.
            </Typography>
          </div>
          {summary.visits ? (
            <DailyCharts daily={data.daily} />
          ) : (
            <EmptyState
              title="No visits in this range"
              description="Choose another date range to inspect attendance. The CSV uses these same dates and definitions."
            />
          )}
          <DailyTable key={`${data.start}/${data.end}/${data.timezone}`} daily={data.daily} />
        </>
      ) : null}
    </div>
  )
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <dt className="text-sm font-medium">{label}</dt>
      <dd className="mt-1">
        <Typography variant="stat">{value}</Typography>
        <Typography variant="small">{detail}</Typography>
      </dd>
    </div>
  )
}
