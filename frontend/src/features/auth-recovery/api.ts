import { api } from '@/lib/api/client'
import type { PasswordResetInput, PasswordResetRequest } from '@/lib/api/schema.gen'

interface RecoveryReply {
  message: string
}
export function requestPasswordReset(input: PasswordResetRequest) {
  return api<RecoveryReply>('/api/auth/password-reset/request', {
    method: 'POST',
    body: { ...input },
  })
}
export function completePasswordReset(input: PasswordResetInput) {
  return api<RecoveryReply>('/api/auth/password-reset/complete', {
    method: 'POST',
    body: { ...input },
  })
}
