import { createFileRoute, useRouter } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { ResetPasswordForm } from '@/features/auth-recovery/forms'
import { recoveryToken } from '@/features/auth-recovery/validation'

export const Route = createFileRoute('/reset-password')({
  validateSearch: (search: Record<string, unknown>): { token?: string } =>
    typeof search.token === 'string' ? { token: search.token } : {},
  component: ResetPasswordPage,
})
function ResetPasswordPage() {
  const search = Route.useSearch()
  const [token] = useState(() => recoveryToken(search.token))
  const router = useRouter()
  useEffect(() => {
    // Keep the emailed token in this component's memory, not browser history.
    const url = new URL(window.location.href)
    if (url.searchParams.has('token')) {
      url.searchParams.delete('token')
      router.history.replace(url.pathname + url.search + url.hash)
    }
  }, [router])
  return <ResetPasswordForm token={token} />
}
