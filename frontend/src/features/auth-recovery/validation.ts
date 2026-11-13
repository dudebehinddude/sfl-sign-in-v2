/** Format check only. The server checks ownership, expiry and single use. */
export function recoveryToken(value: unknown): string | null {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{20,256}$/.test(value) ? value : null
}
