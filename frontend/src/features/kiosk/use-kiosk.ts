import { useQueryClient } from '@tanstack/react-query'
import { useReducer, useRef } from 'react'

import { ApiError, NetworkError, errorMessage } from '@/lib/api/client'
import type { Occupancy } from '@/lib/api/types'
import { kioskKeys, publicKeys } from '@/lib/query-keys'
import { sendKioskRequest } from './api'
import { initialKioskState, kioskReducer, type Feedback, type KioskRequest } from './machine'

function isRetryable(error: unknown) {
  // A lost response may have committed. Refresh state; never replay the toggle.
  return error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)
}

export function useKiosk() {
  const [state, dispatch] = useReducer(kioskReducer, initialKioskState)
  const inFlight = useRef(false)
  const client = useQueryClient()
  const lastScan = useRef({ identifier: '', at: 0 })

  const execute = async (request: KioskRequest) => {
    if (inFlight.current) return
    inFlight.current = true
    dispatch({ type: 'submit', request })
    try {
      const response = await sendKioskRequest(request)
      dispatch({ type: 'succeeded', response })
      // The live snapshot normally arrives first; refetch only if it has not.
      const cached = client.getQueryData<Occupancy>(publicKeys.occupancy())
      if (!cached || cached.revision < response.revision) {
        client.invalidateQueries({ queryKey: publicKeys.occupancy() })
      }
      client.invalidateQueries({ queryKey: kioskKeys.state() })
    } catch (error) {
      void client.invalidateQueries({ queryKey: publicKeys.occupancy() })
      void client.invalidateQueries({ queryKey: kioskKeys.state() })
      dispatch({
        type: 'failed',
        message: errorMessage(error),
        retryable: isRetryable(error),
        status: error instanceof ApiError ? error.status : undefined,
      })
    } finally {
      inFlight.current = false
    }
  }

  const { phase } = state

  return {
    state,
    busy: phase.name === 'sending',
    scan: (identifier: string) => {
      const at = Date.now()
      if (
        inFlight.current ||
        (lastScan.current.identifier === identifier && at - lastScan.current.at < 750)
      )
        return
      lastScan.current = { identifier, at }
      return execute({ kind: 'tap', identifier })
    },
    checkState: () => {
      void client.invalidateQueries({ queryKey: publicKeys.occupancy() })
      void client.invalidateQueries({ queryKey: kioskKeys.state() })
      dispatch({ type: 'cancel' })
    },
    register: (fields: { first_name: string; last_name: string; email: string }) => {
      if (phase.name !== 'registering') return
      void execute({ kind: 'register', identifier: phase.identifier, ...fields })
    },
    keyholder: (
      action: Extract<KioskRequest, { kind: 'keyholder' }>['action'],
      extra: { target_identifier?: string; sign_out_current_keyholder?: boolean } = {},
    ) => {
      if (phase.name !== 'keyholder') return
      void execute({
        kind: 'keyholder',
        identifier: phase.identifier,
        expected_shift_id: phase.expectedShiftId,
        action,
        ...extra,
      })
    },
    cancel: (feedback?: Omit<Feedback, 'id'>) => {
      if (!inFlight.current) dispatch({ type: 'cancel', feedback })
    },
    dismissFeedback: (id: number) => dispatch({ type: 'dismissFeedback', id }),
  }
}

export type KioskController = ReturnType<typeof useKiosk>
