import { Link } from '@tanstack/react-router'
import { Typography } from '@/components/typography'
import { UserAvatar } from '@/components/user-avatar'
import type { ForgottenPerson } from '@/features/kiosk/api'
import type { KioskState, Occupancy } from '@/lib/api/types'
import { formatNumber } from '@/lib/format'

export function GlancePanel({ occupancy, kiosk, leaderboard }: {
  occupancy: Occupancy | undefined
  kiosk: KioskState | undefined
  leaderboard: ForgottenPerson[] | undefined
}) {
  const keyholder = occupancy?.lab.keyholder ?? kiosk?.lab.keyholder ?? null
  const stats = kiosk?.stats
  const forgotten = leaderboard?.filter(person => person.forgotten_signouts > 0)
  return <section aria-label="Current keyholder and attendance" className="station-glance rounded-lg border bg-card shadow-sm">
    <Typography variant="h2">Info at a glance</Typography>
    <div className="station-holder">
      <p className="station-holder-name">Current Keyholder: {keyholder?.display_name ?? 'None'}</p>
      <UserAvatar name={keyholder?.display_name ?? 'No keyholder'} url={keyholder?.avatar_url} className="station-holder-photo" />
    </div>
    <table className="station-glance-stats"><tbody>
      <tr><th scope="row"># in Building</th><td>{occupancy ? occupancy.occupants.length : '—'}</td></tr>
      <tr><th scope="row">Unique Today</th><td>{stats?.unique_visitors_today ?? '—'}</td></tr>
      <tr><th scope="row">Open Printers</th><td>—</td></tr>
      <tr><th scope="row">Hours (Week)</th><td>{formatNumber(stats?.weekly_hours)}</td></tr>
    </tbody></table>
    <div className="station-forgotten">
      <p>You forgot to sign out. Mongo is <strong>appalled.</strong></p>
      {forgotten?.length ? <ol>{forgotten.map(person => <li key={`${person.display_name}-${person.total_visits}-${person.forgotten_signouts}`}>{person.display_name} - {person.ratio.toFixed(2)}</li>)}</ol> : <p className="mt-2 text-muted-foreground">No forgotten sign-outs.</p>}
    </div>
    <Link to="/occupancy" className="inline-flex min-h-11 items-center text-sm text-primary underline-offset-4 hover:underline">Who is in the lab</Link>
  </section>
}
