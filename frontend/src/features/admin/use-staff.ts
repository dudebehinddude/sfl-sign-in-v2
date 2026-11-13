import { useSession } from '@/features/auth/session'
import { staffKeys } from '@/lib/query-keys'

/** Session plus cache keys scoped to the signed-in principal. */
export function useStaff() {
  const session = useSession()
  return { ...session, keys: staffKeys(session.user?.id ?? 'anonymous') }
}
