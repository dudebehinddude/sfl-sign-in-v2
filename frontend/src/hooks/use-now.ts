import { useSyncExternalStore } from 'react'

let now = Date.now()
const listeners = new Set<() => void>()
let timer: ReturnType<typeof setInterval> | undefined
const subscribe = (listener: () => void) => {
  listeners.add(listener)
  if (!timer)
    timer = setInterval(() => {
      now = Date.now()
      for (const notify of listeners) notify()
    }, 30_000)
  return () => {
    listeners.delete(listener)
    if (!listeners.size) {
      clearInterval(timer)
      timer = undefined
    }
  }
}
export function useNow() {
  return useSyncExternalStore(
    subscribe,
    () => now,
    () => now,
  )
}
