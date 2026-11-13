import { TrainingBadgeList } from '@/components/training-badge'
import { Typography } from '@/components/typography'
import { UserAvatar } from '@/components/user-avatar'
import type { Occupant } from '@/lib/api/types'

export function OccupantTable({ occupants }: { occupants: Occupant[] }) {
  return (
    <ul className="min-w-0 divide-y rounded-xl border px-3" aria-label="People in the lab">
      {occupants.map((occupant) => (
        <li
          key={occupant.id}
          className="grid min-w-0 grid-cols-[2.25rem_minmax(0,1fr)] items-center gap-x-3 gap-y-1 py-2 sm:grid-cols-[2.25rem_minmax(8rem,0.65fr)_minmax(0,1fr)]"
        >
          <UserAvatar
            name={occupant.display_name}
            url={occupant.avatar_url}
            className="col-start-1 row-span-2 size-9 sm:row-span-1"
          />
          <Typography variant="body" as="span" className="min-w-0 break-words font-medium">
            {occupant.display_name}
          </Typography>
          <div className="col-start-2 min-w-0 sm:col-start-3">
            <TrainingBadgeList badges={occupant.badges} />
          </div>
        </li>
      ))}
    </ul>
  )
}
