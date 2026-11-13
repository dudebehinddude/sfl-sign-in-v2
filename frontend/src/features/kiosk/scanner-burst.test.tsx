import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ScannerBurstDetector, useScannerBurst } from './scanner-burst'
import { RegistrationDialog } from '@/routes/kiosk/_components/registration-dialog'

it('recognizes only complete fast scans and rejects overlong IDs and slow typing', () => {
  const detector = new ScannerBurstDetector()
  let time = 0
  const type = (value: string, gap = 5) => {
    let result: string | null = null
    for (const key of [...value, 'Enter']) {
      time += gap
      result = detector.push({ key, time })
    }
    return result
  }
  expect(type('800000001')).toBe('800000001')
  expect(type('1800000001')).toBeNull()
  expect(type('800000001', 90)).toBeNull()
  expect(type('80000')).toBeNull()
})
it('a scanner at a registration field starts the new card and cannot submit the old form', () => {
  let time = 0
  const scan = vi.fn()
  const submit = vi.fn()
  render(
    <RegistrationDialog
      identifier="800000001"
      busy={false}
      onSubmit={submit}
      onCancel={vi.fn()}
      onScanDuringForm={scan}
      clock={() => (time += 5)}
    />,
  )
  const field = screen.getByLabelText('First name')
  for (const key of '800000002') fireEvent.keyDown(field, { key })
  expect(fireEvent.keyDown(field, { key: 'Enter' })).toBe(false)
  expect(scan).toHaveBeenCalledExactlyOnceWith('800000002')
  expect(submit).not.toHaveBeenCalled()
})
function Harness({ onScan }: { onScan: (id: string) => void }) {
  useScannerBurst(onScan, true, () => 1)
  return <input aria-label="Scanner" data-scan-input="" />
}
it('leaves dedicated scanner fields to their form instead of double-dispatching', () => {
  const scan = vi.fn()
  render(<Harness onScan={scan} />)
  const field = screen.getByLabelText('Scanner')
  for (const key of '800000002') fireEvent.keyDown(field, { key })
  expect(fireEvent.keyDown(field, { key: 'Enter' })).toBe(true)
  expect(scan).not.toHaveBeenCalled()
})
