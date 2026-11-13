import { expect, it } from 'vitest'
import { initialKioskState, kioskReducer } from './machine'
import { keyholderScanIntent } from './keyholder-intent'

it('abandons registration fields when another card scans', () => {
  let state = kioskReducer(initialKioskState, {
    type: 'submit',
    request: { kind: 'tap', identifier: '800000001' },
  })
  state = kioskReducer(state, {
    type: 'succeeded',
    response: {
      status: 'registration_required',
      revision: 1,
      message: '',
      identifier: '800000001',
    },
  })
  expect(state.phase).toEqual({ name: 'registering', identifier: '800000001' })
  state = kioskReducer(state, { type: 'submit', request: { kind: 'tap', identifier: '800000002' } })
  expect(state.phase).toEqual({
    name: 'sending',
    request: { kind: 'tap', identifier: '800000002' },
    from: undefined,
  })
})
it('preserves the exact expected shift and supports opening with no shift', () => {
  const sending = kioskReducer(initialKioskState, {
    type: 'submit',
    request: { kind: 'tap', identifier: '800000001' },
  })
  for (const expected_shift_id of [null, 'shift-1']) {
    const state = kioskReducer(sending, {
      type: 'succeeded',
      response: {
        status: 'keyholder_action_required',
        revision: 1,
        message: 'Confirm',
        actions: ['open'],
        expected_shift_id,
      },
    })
    expect(state.phase).toMatchObject({ name: 'keyholder', expectedShiftId: expected_shift_id })
  }
})
it('does not retain a replayable tap after a lost network response', () => {
  const sending = kioskReducer(initialKioskState, {
    type: 'submit',
    request: { kind: 'tap', identifier: '800000001' },
  })
  const uncertain = kioskReducer(sending, {
    type: 'failed',
    message: 'Connection lost',
    retryable: true,
  })
  expect(uncertain.phase).toEqual({ name: 'uncertain', message: 'Connection lost' })
  expect(
    kioskReducer(sending, { type: 'submit', request: { kind: 'tap', identifier: '800000002' } }),
  ).toBe(sending)
})
it('a different card supersedes an opening/takeover prompt but hands off at departure', () => {
  expect(keyholderScanIntent('open', ['open'], '800000001', '800000002')).toEqual({
    type: 'new-scan',
    identifier: '800000002',
  })
  expect(
    keyholderScanIntent('takeover', ['override', 'continue'], '800000001', '800000001'),
  ).toEqual({ type: 'confirm', action: 'override' })
  expect(keyholderScanIntent('departure', ['close', 'handoff'], '800000001', '800000002')).toEqual({
    type: 'handoff',
    target: '800000002',
  })
})
