import { useState } from 'react'
import { Typography } from '@/components/typography'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatCalendarDate, formatNumber } from '@/lib/format'
import type { DailyMetrics } from './data'

const PAGE_SIZE = 30
export function DailyTable({ daily }: { daily: DailyMetrics[] }) {
  const [requestedPage, setPage] = useState(1)
  const totalPages = Math.max(1, Math.ceil(daily.length / PAGE_SIZE))
  const page = Math.min(requestedPage, totalPages)
  const visible = daily.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  return (
    <section className="flex flex-col gap-3" aria-labelledby="daily-data-heading">
      <Typography variant="h3" id="daily-data-heading">
        Daily data
      </Typography>
      <div className="rounded-lg border">
        <Table>
          <TableCaption className="sr-only">
            Daily visits, distinct visitors, and finalized person-hours in the selected reporting
            range.
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Visits</TableHead>
              <TableHead className="text-right">Unique visitors</TableHead>
              <TableHead className="text-right">Finalized hours</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((day) => (
              <TableRow key={day.date}>
                <TableCell>{formatCalendarDate(day.date)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {day.visits.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {day.unique_visitors.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatNumber(day.total_hours)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Typography variant="small">
          A visit can overlap more than one day. Daily unique visitors do not add up to the range's
          unique visitors.
        </Typography>
        {totalPages > 1 ? (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </Button>
            <span className="text-sm tabular-nums">
              {page} / {totalPages}
            </span>
            <Button
              size="sm"
              variant="outline"
              disabled={page === totalPages}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  )
}
