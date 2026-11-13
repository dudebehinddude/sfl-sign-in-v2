import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errorMessage } from '@/lib/api/client'
import type { StaffTopic } from '@/lib/query-keys'
import { useStaff } from './use-staff'

/**
 * Staff mutations invalidate their own topics on success so the change shows
 * immediately; the admin socket then delivers the same invalidation to every
 * other open dashboard.
 */
export function useStaffMutation<TInput, TResult>({
  mutationFn,
  topics,
  success,
}: {
  mutationFn: (input: TInput) => Promise<TResult>
  topics: StaffTopic[]
  success: string | ((result: TResult) => string)
}) {
  const client = useQueryClient()
  const { keys } = useStaff()
  return useMutation({
    mutationFn,
    onSuccess: (result) => {
      toast.success(typeof success === 'function' ? success(result) : success)
      for (const topic of topics) client.invalidateQueries({ queryKey: keys.topic(topic) })
    },
    onError: (error) => toast.error(errorMessage(error)),
  })
}
