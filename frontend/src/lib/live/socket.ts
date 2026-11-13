export function isStale(status: LiveStatus) {
  return status === 'reconnecting' || status === 'closed'
}

export type LiveStatus = 'connecting' | 'live' | 'reconnecting' | 'closed'

export interface LiveMessageContext {
  /** Increments for every new socket; the first message of each is a fresh snapshot. */
  connectionId: number
  firstOfConnection: boolean
}

export interface LiveSocketOptions {
  path: string
  onMessage: (message: LiveMessage, context: LiveMessageContext) => void
  onReconnected?: (connectionId: number) => void
  onAuthRejected?: (code: number) => void
  WebSocketImpl?: typeof WebSocket
  /** Base for exponential backoff; capped at maxDelayMs. */
  baseDelayMs?: number
  maxDelayMs?: number
}

export interface LiveMessage {
  type: string
  topic?: string
  topics?: string[]
  revision?: number
  resnapshot?: boolean
  data?: unknown
}

const AUTH_CLOSE_CODES = new Set([1008, 4401, 4403])
const HEARTBEAT_MS = 25_000
const HEARTBEAT_GRACE_MS = 15_000

export function liveUrl(
  path: string,
  loc: Pick<Location, 'protocol' | 'host'> = window.location,
): string {
  const scheme = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${scheme}//${loc.host}${path}`
}

/**
 * Reconnecting subscription socket. It never polls REST: data arrives as
 * server snapshots/invalidations, and every new connection starts with a
 * fresh snapshot from the server, which consumers treat as authoritative.
 */
export class LiveSocket {
  private socket: WebSocket | null = null
  private status: LiveStatus = 'closed'
  private listeners = new Set<(status: LiveStatus) => void>()
  private connectionId = 0
  private receivedOnConnection = false
  private attempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private lastMessageAt = 0
  // Only enforce heartbeat timeouts once the server has proven it answers pings.
  private serverAnswersPings = false
  private stopped = true
  private readonly options: Required<Pick<LiveSocketOptions, 'baseDelayMs' | 'maxDelayMs'>> &
    LiveSocketOptions

  constructor(options: LiveSocketOptions) {
    this.options = { baseDelayMs: 500, maxDelayMs: 10_000, ...options }
  }

  getStatus = () => this.status

  subscribe = (listener: (status: LiveStatus) => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  start() {
    if (!this.stopped) return
    this.stopped = false
    window.addEventListener('online', this.reconnectNow)
    document.addEventListener('visibilitychange', this.onVisibility)
    this.open()
  }

  stop() {
    this.stopped = true
    window.removeEventListener('online', this.reconnectNow)
    document.removeEventListener('visibilitychange', this.onVisibility)
    this.clearTimers()
    const socket = this.socket
    this.socket = null
    if (socket) {
      socket.close(1000)
    }
    this.setStatus('closed')
  }

  private setStatus(status: LiveStatus) {
    if (this.status === status) return
    this.status = status
    for (const listener of this.listeners) listener(status)
  }

  private open() {
    const Impl = this.options.WebSocketImpl ?? WebSocket
    this.setStatus(this.connectionId === 0 ? 'connecting' : 'reconnecting')
    const socket = new Impl(liveUrl(this.options.path))
    this.socket = socket
    this.connectionId += 1
    this.receivedOnConnection = false
    const connectionId = this.connectionId

    socket.addEventListener('open', () => {
      if (this.socket !== socket || this.stopped) return
      this.attempts = 0
      this.lastMessageAt = Date.now()
      this.startHeartbeat()
    })
    socket.addEventListener('message', (event) => {
      if (this.socket !== socket || this.stopped) return
      this.lastMessageAt = Date.now()
      let message: LiveMessage
      try {
        message = JSON.parse(String(event.data)) as LiveMessage
      } catch {
        return
      }
      if (message.type === 'pong') {
        this.serverAnswersPings = true
        return
      }
      // Server keepalive: proves liveness but carries no data, so it must not
      // count as the connection's authoritative first message.
      if (message.type === 'ping') return
      const firstOfConnection = !this.receivedOnConnection
      this.receivedOnConnection = true
      this.setStatus('live')
      if (firstOfConnection && connectionId > 1) this.options.onReconnected?.(connectionId)
      this.options.onMessage(message, { connectionId, firstOfConnection })
    })
    socket.addEventListener('close', (event) => {
      if (this.socket !== socket) return
      this.socket = null
      this.clearTimers()
      if (AUTH_CLOSE_CODES.has(event.code)) this.options.onAuthRejected?.(event.code)
      if (!this.stopped) this.scheduleReconnect()
    })
  }

  private scheduleReconnect() {
    this.setStatus('reconnecting')
    const { baseDelayMs, maxDelayMs } = this.options
    const delay =
      Math.min(maxDelayMs, baseDelayMs * 2 ** this.attempts) * (0.75 + Math.random() * 0.5)
    this.attempts += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.open()
    }, delay)
  }

  private reconnectNow = () => {
    if (this.stopped || this.socket) return
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this.attempts = 0
    this.open()
  }

  private onVisibility = () => {
    if (document.visibilityState === 'visible') this.reconnectNow()
  }

  private startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      const socket = this.socket
      if (!socket || socket.readyState !== socket.OPEN) return
      if (
        this.serverAnswersPings &&
        Date.now() - this.lastMessageAt > HEARTBEAT_MS + HEARTBEAT_GRACE_MS
      ) {
        socket.close(4000, 'heartbeat timeout')
        return
      }
      socket.send(JSON.stringify({ type: 'ping' }))
    }, HEARTBEAT_MS)
  }

  private clearTimers() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer)
    this.reconnectTimer = null
    this.heartbeatTimer = null
  }
}
