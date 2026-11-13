import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/router'

let router: ReturnType<typeof createAppRouter> | undefined
let client: QueryClient | undefined
afterEach(() => {
  cleanup()
  router?.history.destroy()
  client?.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.history.replaceState({}, '', '/')
})
it('keeps a valid email link usable after removing its token from the real browser URL', async () => {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  const token = 'synthetic_route_recovery_token_1234567'
  window.history.replaceState({}, '', `/reset-password?token=${token}`)
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ message: 'Password updated; sign in with your new password' })),
    )
  vi.stubGlobal('fetch', fetch)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  router = createAppRouter(client)
  await router.load()
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  expect(await screen.findByRole('heading', { name: 'Choose a new password' })).toBeVisible()
  await waitFor(() => expect(window.location.search).toBe(''))
  expect(window.location.pathname).toBe('/reset-password')
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('New password'), {
    target: { value: 'route-fixture-password' },
  })
  fireEvent.change(screen.getByLabelText('Confirm new password'), {
    target: { value: 'route-fixture-password' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  expect(await screen.findByRole('heading', { name: 'Password updated' })).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls[0][0]).toBe('/api/auth/password-reset/complete')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    token,
    password: 'route-fixture-password',
  })
})
