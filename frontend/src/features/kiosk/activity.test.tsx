import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { RecentActivity } from '@/routes/kiosk/_components/recent-activity'

afterEach(cleanup)
it('shows the original four columns with both actual times from the same visit', () => {
  render(<RecentActivity activity={[
    { user_id: 'one', display_name: 'First Visitor', enter_time: '2026-11-09T18:00:00Z', exit_time: '2026-11-09T19:05:00Z', occurred_at: '2026-11-09T19:05:00Z', action: 'signed_out' },
    { user_id: 'two', display_name: 'Still Here', enter_time: '2026-11-09T17:00:00Z', exit_time: null, occurred_at: '2026-11-09T17:00:00Z', action: 'signed_in' },
  ]} />)
  expect(screen.getAllByRole('columnheader').map(cell => cell.textContent)).toEqual(['Time In', 'Time Out', 'Name', 'Description'])
  const rows = screen.getAllByRole('row')
  expect(within(rows[1]).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['1:00 PM', '2:05 PM', 'First Visitor', 'OUT'])
  expect(within(rows[2]).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['12:00 PM', '—', 'Still Here', 'IN'])
})
