import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { useKiosk } from './use-kiosk'

afterEach(() => vi.unstubAllGlobals())

it.each([
  [
    'interrupted body',
    () => new Response(new ReadableStream({
      start(controller) {
        controller.error(new TypeError('connection lost after headers'))
      },
    })),
  ],
  ['malformed JSON', () => new Response('{')],
  ['unknown status', () => Response.json({ status: 'unexpected', message: '', revision: 1 })],
  ['incomplete command result', () => Response.json({ status: 'signed_in' })],
  [
    'invalid keyholder prompt',
    () => Response.json({
      status: 'keyholder_action_required',
      message: '',
      revision: 1,
      actions: ['open'],
    }),
  ],
])('keeps a %s uncertain without replaying the tap', async (_name, response) => {
  const fetch = vi.fn().mockResolvedValue(response())
  vi.stubGlobal('fetch', fetch)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(useKiosk, { wrapper })
  await act(async () => {
    await result.current.scan('800000001')
  })
  expect(result.current.state.phase.name).toBe('uncertain')
  expect(fetch).toHaveBeenCalledTimes(1)
  act(() => result.current.checkState())
  expect(result.current.state.phase.name).toBe('ready')
  expect(fetch).toHaveBeenCalledTimes(1)
  client.clear()
})
