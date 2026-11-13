import { useSyncExternalStore } from 'react'

const QUERY = '(max-width: 767px)'
const subscribe = (notify: () => void) => {
  const media = window.matchMedia(QUERY)
  media.addEventListener('change', notify)
  return () => media.removeEventListener('change', notify)
}

export function useIsMobile() {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  )
}
