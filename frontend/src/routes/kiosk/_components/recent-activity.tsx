import { Typography } from '@/components/typography'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { KioskActivity } from '@/lib/api/types'
import { formatTime } from '@/lib/format'

export function RecentActivity({ activity }: { activity: KioskActivity[] | undefined }) {
  return <section aria-labelledby="recent-activity" className="station-activity">
    <Typography variant="h2" id="recent-activity">Recent Activity (Today)</Typography>
    {activity?.length === 0 ? <Typography variant="muted">No sign-ins today.</Typography> : (
      <Table aria-label="Today's sign-ins and sign-outs">
        <TableHeader><TableRow>
          <TableHead>Time In</TableHead><TableHead>Time Out</TableHead><TableHead>Name</TableHead><TableHead>Description</TableHead>
        </TableRow></TableHeader>
        <TableBody>{activity?.map(row => <TableRow key={`${row.user_id}-${row.enter_time}`} className={!row.exit_time ? 'activity-present' : undefined}>
          <TableCell className="whitespace-nowrap">{formatTime(row.enter_time)}</TableCell>
          <TableCell className="whitespace-nowrap">{formatTime(row.exit_time)}</TableCell>
          <TableCell className="font-semibold whitespace-normal">{row.display_name}</TableCell>
          <TableCell>{row.action === 'signed_out' ? 'OUT' : 'IN'}</TableCell>
        </TableRow>)}</TableBody>
      </Table>
    )}
  </section>
}
