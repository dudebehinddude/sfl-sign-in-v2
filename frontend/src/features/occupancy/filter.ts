import type { Occupant, PublicTrainingType } from '@/lib/api/types'

export interface OccupantFilter {
  search: string
  trainingTypeId: string | null
}

export function filterOccupants(occupants: Occupant[], filter: OccupantFilter): Occupant[] {
  const search = filter.search.trim().toLocaleLowerCase()
  return occupants.filter(
    (occupant) =>
      (!search || occupant.display_name.toLocaleLowerCase().includes(search)) &&
      (!filter.trainingTypeId ||
        occupant.badges.some((badge) => badge.training_type_id === filter.trainingTypeId)),
  )
}

export interface TrainingCount {
  id: string
  name: string
  icon_key: string
  count: number
}

/** Count people, not repeated manual/Canvas evidence for the same training. */
export function trainingCounts(
  occupants: Occupant[],
  filter: OccupantFilter,
  catalog: Pick<PublicTrainingType, 'id' | 'name' | 'icon_key'>[] = [],
): {
  total: number
  trainings: TrainingCount[]
} {
  const base = filterOccupants(occupants, { ...filter, trainingTypeId: null })
  const counts = new Map<string, TrainingCount>()
  for (const type of catalog)
    counts.set(type.id, { id: type.id, name: type.name, icon_key: type.icon_key, count: 0 })
  for (const occupant of base) {
    const seen = new Set<string>()
    for (const badge of occupant.badges) {
      if (seen.has(badge.training_type_id)) continue
      seen.add(badge.training_type_id)
      const entry = counts.get(badge.training_type_id) ?? {
        id: badge.training_type_id,
        name: badge.name,
        icon_key: badge.icon_key,
        count: 0,
      }
      entry.count += 1
      counts.set(badge.training_type_id, entry)
    }
  }
  return {
    total: base.length,
    // Map insertion order keeps the canonical catalog sequence. Uncatalogued
    // badges follow it in the order they first appear in the input.
    trainings: [...counts.values()],
  }
}
