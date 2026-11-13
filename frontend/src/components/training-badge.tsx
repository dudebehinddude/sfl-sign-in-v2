import { GraduationCapIcon } from 'lucide-react'
import { useState } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Badge as BadgeDto } from '@/lib/api/types'

const ICON_ALIASES: Record<string, string> = {
  'door-open': 'orientation',
  'clipboard-check': 'policies',
  printer: '3d-printer',
  zap: 'laser-cutter',
  droplets: 'resin-printer',
  waves: 'waterjet',
}
const ICONS = new Set(['orientation', 'policies', '3d-printer', 'laser-cutter', 'resin-printer', 'waterjet'])

export function TrainingIcon({ name, iconKey, completed = false }: {
  name: string
  iconKey: string
  completed?: boolean
}) {
  const [failedSource, setFailedSource] = useState<string | null>(null)
  const key = ICON_ALIASES[iconKey] ?? iconKey
  const source = /^training-icons\/[a-f0-9]{32}\.png$/.test(iconKey) ? `/media/${iconKey}` : ICONS.has(key) ? `/training-icons/${key}-icon.png` : null
  const description = completed ? `Completed ${name}.` : name
  return (
    <Tooltip>
      <TooltipTrigger
        type="button"
        aria-label={description}
        className="inline-flex size-10 shrink-0 items-center justify-center rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        {source && failedSource !== source ? (
          <img src={source} alt="" className="size-9 object-contain" onError={() => setFailedSource(source)} />
        ) : <GraduationCapIcon aria-hidden className="size-7 text-muted-foreground" />}
      </TooltipTrigger>
      <TooltipContent>{description}</TooltipContent>
    </Tooltip>
  )
}

export function TrainingBadge({ badge }: { badge: Pick<BadgeDto, 'name' | 'icon_key'> }) {
  return <TrainingIcon name={badge.name} iconKey={badge.icon_key} completed />
}

export function TrainingBadgeList({ badges }: { badges: BadgeDto[] }) {
  if (!badges.length) return <span className="text-xs text-muted-foreground">No trainings</span>
  return (
    <ul className="flex min-w-0 flex-wrap items-center gap-1" aria-label="Completed trainings">
      {badges.map(badge => <li key={badge.training_type_id}><TrainingBadge badge={badge} /></li>)}
    </ul>
  )
}
