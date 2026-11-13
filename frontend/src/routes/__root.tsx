import type { QueryClient } from '@tanstack/react-query'
import { Link, Outlet, createRootRouteWithContext } from '@tanstack/react-router'

import { TooltipProvider } from '@/components/ui/tooltip'
import { Typography } from '@/components/typography'
import { Button } from '@/components/ui/button'

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: () => <TooltipProvider><Outlet /></TooltipProvider>,
  notFoundComponent: NotFound,
})

function NotFound() {
  return (
    <main className="mx-auto flex min-h-svh max-w-lg flex-col items-start justify-center gap-4 p-6">
      <Typography variant="h1">Page not found</Typography>
      <Typography variant="muted">
        This address does not match any page in the sign-in system.
      </Typography>
      <Button nativeButton={false} render={<Link to="/" />}>
        Go to the homepage
      </Button>
    </main>
  )
}
