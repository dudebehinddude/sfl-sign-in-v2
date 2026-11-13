// Caches are partitioned by audience. Staff keys carry the principal id so a
// different login can never read a previous user's cached admin data, and the
// whole client cache is cleared on logout.

export const publicKeys = {
  all: ['public'] as const,
  occupancy: () => ['public', 'occupancy'] as const,
  trainingTypes: () => ['public', 'training-types'] as const,
}

export const kioskKeys = {
  all: ['kiosk'] as const,
  state: () => ['kiosk', 'state'] as const,
  leaderboard: () => ['kiosk', 'leaderboard'] as const,
}

export const authKeys = {
  me: () => ['auth', 'me'] as const,
}

export function staffKeys(principalId: string) {
  const base = ['staff', principalId] as const
  return {
    all: base,
    topic: (topic: StaffTopic, ...rest: unknown[]) => [...base, topic, ...rest] as const,
  }
}

// Topic names match the backend change-event topics in backend/app/events.py.
export const STAFF_TOPICS = [
  'overview',
  'profile',
  'users',
  'roles',
  'training-types',
  'trainings',
  'visits',
  'keyholders',
  'metrics',
  'canvas',
  'printing',
  'audit',
  'database',
  'storage',
] as const

export type StaffTopic = (typeof STAFF_TOPICS)[number]

// Server topic -> cached staff topics that depend on it. Data shown on the
// overview, metrics and audit pages is derived from many tables, so most
// changes also invalidate those.
const DERIVED: StaffTopic[] = ['overview', 'audit']
export const TOPIC_DEPENDENTS: Record<string, StaffTopic[]> = {
  occupancy: ['visits', 'keyholders', 'metrics', 'profile', ...DERIVED],
  users: ['users', 'trainings', 'visits', 'canvas', 'profile', ...DERIVED],
  roles: ['users', 'roles', ...DERIVED],
  'training-types': ['training-types', 'trainings', 'users', 'canvas', 'profile', ...DERIVED],
  trainings: ['trainings', 'users', 'profile', ...DERIVED],
  visits: ['visits', 'metrics', 'profile', ...DERIVED],
  keyholders: ['keyholders', 'visits', ...DERIVED],
  canvas: ['canvas', 'trainings', 'users', ...DERIVED],
  printing: ['printing', ...DERIVED],
  email: ['canvas', ...DERIVED],
  // Role, password and session changes; the session query itself is refreshed separately.
  permissions: ['users', 'roles', ...DERIVED],
  audit: ['audit'],
  storage: ['storage', 'audit'],
}

export function staffTopicsFor(serverTopics: string[]): StaffTopic[] | 'all' {
  const result = new Set<StaffTopic>()
  for (const topic of serverTopics) {
    const mapped = TOPIC_DEPENDENTS[topic]
    if (!mapped) return 'all'
    for (const item of mapped) result.add(item)
  }
  return [...result]
}
