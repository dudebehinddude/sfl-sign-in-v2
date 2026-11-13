import { QueryClient } from '@tanstack/react-query'
import { createRouter } from '@tanstack/react-router'

import { isStatus } from '@/lib/api/client'
import { routeTree } from './routeTree.gen'

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Live sockets invalidate caches; never poll or refetch on focus.
        refetchOnWindowFocus: false,
        refetchInterval: false,
        staleTime: 30_000,
        retry: (count, error) => !isStatus(error, 400, 401, 403, 404, 422) && count < 2,
      },
    },
  })
}

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({
    routeTree,
    context: { queryClient },
    defaultPreload: 'intent',
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
  })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
