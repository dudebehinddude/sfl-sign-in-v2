import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PropsWithChildren } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { NetworkError } from '@/lib/api/client'
import type { TapResponse } from '@/lib/api/types'
import { sendKioskRequest } from './api'
import { useKiosk } from './use-kiosk'

const registration = (identifier: string): TapResponse => ({
  status: 'registration_required',
  identifier,
  revision: 1,
  message: '',
})

vi.mock('./api', () => ({ sendKioskRequest: vi.fn() }))
afterEach(() => vi.clearAllMocks())
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { ...renderHook(useKiosk, { wrapper }), client }
}
it('allows one command in flight and never repeats an uncertain tap when refreshing state', async () => {
  let reject!: (reason: unknown) => void
  vi.mocked(sendKioskRequest).mockReturnValueOnce(
    new Promise((_resolve, fail) => {
      reject = fail
    }),
  )
  const { result, client } = setup()
  await act(async () => {
    void result.current.scan('800000001')
    void result.current.scan('800000001')
  })
  expect(sendKioskRequest).toHaveBeenCalledTimes(1)
  expect(result.current.busy).toBe(true)
  act(() => result.current.cancel())
  expect(result.current.busy).toBe(true)
  await act(async () => reject(new NetworkError('lost response')))
  expect(result.current.state.phase.name).toBe('uncertain')
  act(() => result.current.checkState())
  expect(result.current.state.phase.name).toBe('ready')
  expect(sendKioskRequest).toHaveBeenCalledTimes(1)
  client.clear()
})
it('registers only the replacement card after another scan abandons the first draft', async () => {
  vi.mocked(sendKioskRequest)
    .mockResolvedValueOnce(registration('800000001'))
    .mockResolvedValueOnce(registration('800000002'))
    .mockResolvedValueOnce({ status: 'signed_in', revision: 2, message: '' })
  const { result, client } = setup()
  await act(async () => {
    await result.current.scan('800000001')
  })
  await waitFor(() =>
    expect(result.current.state.phase).toMatchObject({
      name: 'registering',
      identifier: '800000001',
    }),
  )
  await act(async () => {
    await result.current.scan('800000002')
  })
  await waitFor(() =>
    expect(result.current.state.phase).toMatchObject({
      name: 'registering',
      identifier: '800000002',
    }),
  )
  await act(async () =>
    result.current.register({
      first_name: 'New',
      last_name: 'Visitor',
      email: 'new@charlotte.edu',
    }),
  )
  expect(sendKioskRequest).toHaveBeenLastCalledWith({
    kind: 'register',
    identifier: '800000002',
    first_name: 'New',
    last_name: 'Visitor',
    email: 'new@charlotte.edu',
  })
  client.clear()
})
