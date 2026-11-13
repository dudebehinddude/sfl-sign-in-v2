import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/lib/api/client'
import { staffKeys } from '@/lib/query-keys'
import { CanvasQuizFields } from './quiz-fields'

const { staff } = vi.hoisted(() => ({ staff: vi.fn() }))
vi.mock('@/features/admin/use-staff', () => ({ useStaff: staff }))
vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<typeof import('@/lib/api/client')>()),
  api: vi.fn(),
}))
afterEach(() => vi.clearAllMocks())
function Form() {
  const [assignmentId, setId] = useState('')
  const [score, setScore] = useState('7')
  return (
    <>
      <CanvasQuizFields
        assignmentId={assignmentId}
        onAssignmentId={setId}
        minimumScore={score}
        onMinimumScore={setScore}
      />
      <output aria-label="Saved assignment">{assignmentId}</output>
    </>
  )
}
it('selects the cached assignment ID by quiz title and preserves the explicit score threshold', async () => {
  staff.mockReturnValue({ user: { id: 'staff' }, can: () => true, keys: staffKeys('staff') })
  vi.mocked(api).mockResolvedValue({
    items: [{ id: '202', title: 'Laser safety quiz', points_possible: 10 }],
    refreshed_at: null,
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Form />
    </QueryClientProvider>,
  )
  await screen.findByRole('option', { name: 'Laser safety quiz (10 points)' })
  fireEvent.change(screen.getByLabelText('Canvas quiz'), { target: { value: '202' } })
  expect(screen.getByLabelText('Saved assignment')).toHaveTextContent('202')
  expect(screen.getByLabelText('Minimum passing score')).toHaveValue(7)
  expect(screen.queryByLabelText('Canvas awards level')).toBeNull()
  client.clear()
})
it('does not fetch protected cached choices without Canvas read permission', () => {
  staff.mockReturnValue({ user: { id: 'staff' }, can: () => false, keys: staffKeys('staff') })
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <Form />
    </QueryClientProvider>,
  )
  expect(screen.getByLabelText('Canvas quiz')).toBeDisabled()
  expect(api).not.toHaveBeenCalled()
  client.clear()
})
