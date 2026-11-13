import { TrainingIcon } from '@/components/training-badge'
import { Typography } from '@/components/typography'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { OccupantFilter, TrainingCount } from '@/features/occupancy/filter'

interface TrainingFilterProps {
  counts: { total: number; trainings: TrainingCount[] }
  filter: OccupantFilter
  onChange: (filter: OccupantFilter) => void
}

export function TrainingFilter(props: TrainingFilterProps) {
  const selected = props.counts.trainings.find(
    (training) => training.id === props.filter.trainingTypeId,
  )
  return (
    <>
      <details className="min-w-0 rounded-xl border px-3 sm:hidden">
        <summary className="min-h-11 cursor-pointer content-center text-sm">
          <Typography variant="body" as="span" className="font-medium">
            Training: {selected?.name ?? 'All'}
          </Typography>
        </summary>
        <div className="pb-3">
          <TrainingChoices {...props} />
        </div>
      </details>
      <section className="hidden min-w-0 flex-col gap-2 rounded-xl border p-3 sm:flex">
        <Typography variant="h2">Trainings</Typography>
        <TrainingChoices {...props} />
      </section>
    </>
  )
}

function TrainingChoices({ counts, filter, onChange }: TrainingFilterProps) {
  return (
    <ul aria-label="Filter by training" className="flex min-w-0 flex-col gap-1">
      <li>
        <FilterButton
          label="All trainings"
          count={counts.total}
          selected={filter.trainingTypeId === null}
          onClick={() => onChange({ ...filter, trainingTypeId: null })}
        />
      </li>
      {counts.trainings.map((training) => (
        <li key={training.id}>
          <FilterButton
            label={training.name}
            iconKey={training.icon_key}
            count={training.count}
            selected={filter.trainingTypeId === training.id}
            onClick={() => onChange({ ...filter, trainingTypeId: training.id })}
          />
        </li>
      ))}
    </ul>
  )
}

function FilterButton({
  label,
  iconKey,
  count,
  selected,
  onClick,
}: {
  label: string
  iconKey?: string
  count: number
  selected: boolean
  onClick: () => void
}) {
  return (
    <div className="flex min-w-0 items-center gap-1">
      {iconKey ? (
        <TrainingIcon name={label} iconKey={iconKey} />
      ) : (
        <span aria-hidden className="size-10 shrink-0" />
      )}
      <Button
        variant={selected ? 'default' : 'ghost'}
        aria-pressed={selected}
        onClick={onClick}
        className="h-auto min-h-11 min-w-0 flex-1 justify-between px-2 py-1.5 whitespace-normal text-left"
      >
        <span className="min-w-0 flex-1 break-words">{label}</span>
        <Badge variant={selected ? 'secondary' : 'outline'} className="shrink-0">
          {count}
        </Badge>
      </Button>
    </div>
  )
}
