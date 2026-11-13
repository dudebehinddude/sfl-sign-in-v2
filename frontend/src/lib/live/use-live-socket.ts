import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

import { LiveSocket, type LiveSocketOptions, type LiveStatus } from './socket'

type Handlers = Omit<LiveSocketOptions, 'path' | 'WebSocketImpl'>

export function useLiveSocket(path: string | null, handlers: Handlers): LiveStatus {
  const handlersRef = useRef(handlers)
  useEffect(() => {
    handlersRef.current = handlers
  })

  const [socket, setSocket] = useState<LiveSocket | null>(null)

  useEffect(() => {
    if (!path) return
    const live = new LiveSocket({
      path,
      onMessage: (message, context) => handlersRef.current.onMessage(message, context),
      onReconnected: (id) => handlersRef.current.onReconnected?.(id),
      onAuthRejected: (code) => handlersRef.current.onAuthRejected?.(code),
    })
    setSocket(live)
    live.start()
    return () => {
      live.stop()
      setSocket(null)
    }
  }, [path])

  return useSyncExternalStore(
    socket?.subscribe ?? noopSubscribe,
    socket?.getStatus ?? closedStatus,
    closedStatus,
  )
}

const noopSubscribe = () => () => {}
const closedStatus = (): LiveStatus => 'closed'
