import { createFileRoute } from '@tanstack/react-router'
import { RequestRecoveryForm } from '@/features/auth-recovery/forms'

export const Route = createFileRoute('/recover-password')({ component: RequestRecoveryForm })
