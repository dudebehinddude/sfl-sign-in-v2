import type { KeyholderAction, TapResponse } from '@/lib/api/types'

// Scanner input is an identifier for lab bookkeeping, never a credential.
export type KioskRequest =
  | { kind: 'tap'; identifier: string }
  | {
      kind: 'register'
      identifier: string
      first_name: string
      last_name: string
      email: string
    }
  | {
      kind: 'keyholder'
      identifier: string
      action: KeyholderAction
      expected_shift_id: string | null
      target_identifier?: string
      sign_out_current_keyholder?: boolean
    }

export type FeedbackTone = 'success' | 'info' | 'warning' | 'error'

export interface Feedback {
  id: number
  tone: FeedbackTone
  title: string
  message?: string
}

export type RegisteringPhase = { name: 'registering'; identifier: string; formError?: string }
export type KeyholderPhase = {
  name: 'keyholder'
  identifier: string
  expectedShiftId: string | null
  actions: KeyholderAction[]
  message: string
  displayName: string | null
}

export type Phase =
  | { name: 'ready' }
  // `from` keeps the registration or keyholder dialog on screen while its own command sends.
  | { name: 'sending'; request: KioskRequest; from?: RegisteringPhase | KeyholderPhase }
  | { name: 'uncertain'; message: string }
  | RegisteringPhase
  | KeyholderPhase

export interface KioskMachineState {
  phase: Phase
  feedback: Feedback | null
  nextFeedbackId: number
}

export type KioskEvent =
  | { type: 'submit'; request: KioskRequest }
  | { type: 'succeeded'; response: TapResponse }
  | { type: 'failed'; message: string; retryable: boolean; status?: number }
  | { type: 'cancel'; feedback?: Omit<Feedback, 'id'> }
  | { type: 'dismissFeedback'; id: number }

export const initialKioskState: KioskMachineState = {
  phase: { name: 'ready' },
  feedback: null,
  nextFeedbackId: 1,
}

function withFeedback(
  state: KioskMachineState,
  phase: Phase,
  feedback: Omit<Feedback, 'id'> | null,
): KioskMachineState {
  if (!feedback) return { ...state, phase }
  return {
    phase,
    feedback: { ...feedback, id: state.nextFeedbackId },
    nextFeedbackId: state.nextFeedbackId + 1,
  }
}

function nameOf(response: TapResponse) {
  return response.user?.display_name ?? null
}

function fromResponse(
  state: KioskMachineState,
  request: KioskRequest,
  response: TapResponse,
): KioskMachineState {
  const ready: Phase = { name: 'ready' }
  const name = nameOf(response)
  switch (response.status) {
    case 'signed_in':
      return withFeedback(state, ready, {
        tone: 'success',
        title: name ? `Welcome, ${name}` : 'Signed in',
        message: response.message,
      })
    case 'signed_out':
      return withFeedback(state, ready, {
        tone: 'info',
        title: name ? `Goodbye, ${name}` : 'Signed out',
        message: response.message,
      })
    case 'lab_closed':
      return withFeedback(state, ready, {
        tone: 'warning',
        title: 'The lab is closed',
        message: response.message,
      })
    case 'registration_required':
      return {
        ...state,
        phase: { name: 'registering', identifier: request.identifier },
      }
    case 'keyholder_action_required':
      if (!response.actions?.length || !Object.hasOwn(response, 'expected_shift_id')) {
        return withFeedback(state, ready, {
          tone: 'error',
          title: 'Keyholder step could not start',
          message: 'The server asked for a keyholder decision without its current shift.',
        })
      }
      return {
        ...state,
        phase: {
          name: 'keyholder',
          identifier: request.identifier,
          expectedShiftId: response.expected_shift_id ?? null,
          actions: response.actions,
          message: response.message,
          displayName: name,
        },
      }
  }
}

function continuing(
  phase: Phase,
  request: KioskRequest,
): RegisteringPhase | KeyholderPhase | undefined {
  if (phase.name === 'registering' && request.kind === 'register') return phase
  if (phase.name === 'keyholder' && request.kind === 'keyholder') return phase
  return undefined
}

export function kioskReducer(state: KioskMachineState, event: KioskEvent): KioskMachineState {
  const { phase } = state
  switch (event.type) {
    case 'submit':
      // One command at a time; the input is disabled while sending.
      if (phase.name === 'sending') return state
      // Any new scan supersedes a pending registration or keyholder confirmation,
      // so an abandoned form can never be completed by the next visitor's card.
      return {
        ...state,
        phase: { name: 'sending', request: event.request, from: continuing(phase, event.request) },
      }
    case 'succeeded':
      if (phase.name !== 'sending') return state
      return fromResponse(state, phase.request, event.response)
    case 'failed': {
      if (phase.name !== 'sending') return state
      if (event.retryable) {
        return { ...state, phase: { name: 'uncertain', message: event.message } }
      }
      if (phase.from?.name === 'registering' && event.status === 422) {
        return { ...state, phase: { ...phase.from, formError: event.message } }
      }
      return withFeedback(
        state,
        { name: 'ready' },
        { tone: 'error', title: 'That did not go through', message: event.message },
      )
    }
    case 'cancel':
      return withFeedback(state, { name: 'ready' }, event.feedback ?? null)
    case 'dismissFeedback':
      if (state.feedback?.id !== event.id) return state
      return { ...state, feedback: null }
  }
}

// Mirrors backend TapInput: nine-digit student ID or an issued lab identifier.
const IDENTIFIER = /^(?:\d{9}|[A-Za-z][A-Za-z0-9:_-]{2,63})$/

export function normalizeIdentifier(raw: string): string | null {
  const value = raw.trim()
  return IDENTIFIER.test(value) ? value : null
}
