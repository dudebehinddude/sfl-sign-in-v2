import type { KeyholderAction } from '@/lib/api/types'

export type KeyholderVariant = 'open' | 'takeover' | 'departure'

export function keyholderVariant(actions: KeyholderAction[]): KeyholderVariant {
  if (actions.includes('handoff') || actions.includes('close')) return 'departure'
  if (actions.includes('override')) return 'takeover'
  return 'open'
}

export type ScanIntent =
  | { type: 'confirm'; action: 'open' | 'override' }
  | { type: 'handoff'; target: string }
  | { type: 'own-card' }
  | { type: 'new-scan'; identifier: string }

/**
 * What a card scanned while a keyholder dialog is open means. Rescanning the
 * same card confirms opening or takeover; any other card is the next visitor,
 * which supersedes the pending decision. In the departure dialog another card
 * is the next keyholder receiving the handoff, as in the legacy station.
 */
export function keyholderScanIntent(
  variant: KeyholderVariant,
  actions: KeyholderAction[],
  own: string,
  scanned: string,
): ScanIntent {
  if (variant === 'departure') {
    if (scanned === own) return { type: 'own-card' }
    return actions.includes('handoff')
      ? { type: 'handoff', target: scanned }
      : { type: 'new-scan', identifier: scanned }
  }
  if (scanned !== own) return { type: 'new-scan', identifier: scanned }
  return { type: 'confirm', action: variant === 'takeover' ? 'override' : 'open' }
}
