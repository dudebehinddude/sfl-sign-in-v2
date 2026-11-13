import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { KeyholderDialog } from '@/routes/kiosk/_components/keyholder-dialog'
import {
  RegistrationDialog,
  REGISTRATION_IDLE_MS,
} from '@/routes/kiosk/_components/registration-dialog'
import { ScanForm } from '@/routes/kiosk/_components/scan-form'
import { UNIVERSITY_EMAIL_MESSAGE } from '@/lib/university-email'

afterEach(() => vi.useRealTimers())

function registration(overrides = {}) {
  const submit = vi.fn()
  const cancel = vi.fn()
  render(
    <RegistrationDialog
      identifier="800000001"
      busy={false}
      onSubmit={submit}
      onCancel={cancel}
      onScanDuringForm={vi.fn()}
      {...overrides}
    />,
  )
  return { submit, cancel }
}

it('rejects outside email domains and accepts either university domain case-insensitively', () => {
  const { submit } = registration()
  fireEvent.change(screen.getByLabelText('First name'), { target: { value: ' Ada ' } })
  fireEvent.change(screen.getByLabelText('Last name'), { target: { value: 'Lovelace' } })
  const email = screen.getByLabelText('University email')
  fireEvent.change(email, { target: { value: 'ada@example.org' } })
  const form = email.closest('form')!
  fireEvent.submit(form)
  expect(submit).not.toHaveBeenCalled()
  expect(screen.getByText(UNIVERSITY_EMAIL_MESSAGE)).toBeVisible()
  expect(email).toHaveAttribute('aria-invalid', 'true')
  for (const address of ['Ada@UNCC.EDU', 'ada@charlotte.edu']) {
    fireEvent.change(email, { target: { value: address } })
    fireEvent.submit(form)
    expect(submit).toHaveBeenLastCalledWith({
      first_name: 'Ada',
      last_name: 'Lovelace',
      email: address,
    })
  }
})

it('resets the idle deadline while typing and closes an abandoned registration', () => {
  vi.useFakeTimers()
  const { cancel } = registration()
  act(() => vi.advanceTimersByTime(REGISTRATION_IDLE_MS - 1000))
  fireEvent.change(screen.getByLabelText('First name'), { target: { value: 'Ada' } })
  act(() => vi.advanceTimersByTime(1500))
  expect(cancel).not.toHaveBeenCalled()
  act(() => vi.advanceTimersByTime(REGISTRATION_IDLE_MS - 1500))
  expect(cancel).toHaveBeenCalledExactlyOnceWith('timeout')
})

it('does not timeout or resubmit a registration while its command is sending', () => {
  vi.useFakeTimers()
  const { submit, cancel } = registration({ busy: true })
  act(() => vi.advanceTimersByTime(REGISTRATION_IDLE_MS + 1))
  expect(cancel).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: /Signing in/ })).toBeDisabled()
  fireEvent.submit(screen.getByLabelText('First name').closest('form')!)
  expect(submit).not.toHaveBeenCalled()
})

it('allows a typed card to submit with the touch action and rejects an incomplete card', () => {
  const scan = vi.fn()
  render(
    <ScanForm id="test-card" label="Member ID" placeholder="Scan or type your ID" onScan={scan} />,
  )
  const input = screen.getByLabelText('Member ID')
  fireEvent.change(input, { target: { value: '80000' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(scan).not.toHaveBeenCalled()
  fireEvent.change(input, { target: { value: '800000001' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  expect(scan).toHaveBeenCalledExactlyOnceWith('800000001')
  expect(input).toHaveValue('')
})

it('requires explicit confirmation to close the lab and preserves handoff options', () => {
  const action = vi.fn()
  render(
    <KeyholderDialog
      identifier="800000001"
      actions={['handoff', 'close']}
      message="You are the keyholder."
      occupancy={{
        revision: 1,
        lab: { is_open: true, keyholder: { id: 'own', display_name: 'Current keyholder' } },
        occupants: [
          { id: 'own', display_name: 'Current keyholder', badges: [] },
          { id: 'other', display_name: 'Another visitor', badges: [] },
        ],
      }}
      busy={false}
      onAction={action}
      onCancel={vi.fn()}
      onNewScan={vi.fn()}
    />,
  )
  expect(screen.getByLabelText("Next keyholder's card")).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Close the lab' }))
  expect(action).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm close' }))
  expect(action).toHaveBeenCalledExactlyOnceWith('close')
})
