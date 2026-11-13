import { useEffect, useRef } from 'react'

// Card scanners type nine digits and Enter within a few milliseconds per key.
// People cannot sustain that, so a burst is recognized only when every key
// arrives within MAX_GAP_MS of the previous one.
export const MAX_GAP_MS = 50
const CARD_DIGITS = 9
const IGNORED_KEYS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock'])

/** Elements that handle scans themselves, through their own form submit. */
export const SCAN_INPUT_ATTR = 'data-scan-input'

export interface BurstKey {
  key: string
  time: number
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
}

export class ScannerBurstDetector {
  private digits = ''
  private last = -Infinity

  /** Returns the scanned identifier when this key completes a burst. */
  push(event: BurstKey): string | null {
    if (IGNORED_KEYS.has(event.key)) return null
    const fast = event.time - this.last <= MAX_GAP_MS
    if (/^\d$/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
      this.digits = fast ? this.digits + event.key : event.key
      this.last = event.time
      // Keep overflow invalid; truncating could select a different person.
      if (this.digits.length > CARD_DIGITS + 1) this.digits = this.digits.slice(0, CARD_DIGITS + 1)
      return null
    }
    const complete =
      event.key === 'Enter' &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey &&
      fast &&
      this.digits.length === CARD_DIGITS
        ? this.digits
        : null
    this.reset()
    return complete
  }

  reset() {
    this.digits = ''
    this.last = -Infinity
  }
}

/**
 * Listens in the capture phase so a card scanned while focus sits in a form
 * field or on a button abandons that draft. The Enter never submits it;
 * scan inputs continue to handle their own complete form value.
 */
export function useScannerBurst(
  onScan: (identifier: string) => void,
  enabled = true,
  clock: () => number = Date.now,
) {
  const onScanRef = useRef(onScan)
  useEffect(() => {
    onScanRef.current = onScan
  })

  useEffect(() => {
    if (!enabled) return
    const detector = new ScannerBurstDetector()
    const onKeyDown = (event: KeyboardEvent) => {
      const identifier = detector.push({
        key: event.key,
        time: clock(),
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey,
        altKey: event.altKey,
      })
      if (!identifier) return
      const target = event.target as HTMLElement | null
      if (target?.closest(`[${SCAN_INPUT_ATTR}]`)) return
      event.preventDefault()
      event.stopPropagation()
      onScanRef.current(identifier)
    }
    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [enabled, clock])
}
