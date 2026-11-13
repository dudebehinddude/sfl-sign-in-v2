// Same-origin only: /api, /ws and /media are served on the single APP_PORT, so
// the browser uses this instance’s session cookie. Never add a base URL.

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export class NetworkError extends Error {
  constructor(
    cause: unknown,
    message = 'Could not reach the lab server. Check the network connection and try again.',
  ) {
    super(message)
    this.name = 'NetworkError'
    this.cause = cause
  }
}

export class ResponseError extends NetworkError {
  constructor(cause: unknown) {
    super(cause, 'The server response was interrupted or invalid.')
    this.name = 'ResponseError'
  }
}

let csrfToken: string | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

interface ValidationIssue {
  loc?: (string | number)[]
  msg?: string
}

export function formatErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = (detail as ValidationIssue[])
      .map((issue) => {
        const field = issue.loc?.filter((part) => part !== 'body').join('.')
        return field ? `${field}: ${issue.msg ?? 'invalid'}` : issue.msg
      })
      .filter(Boolean)
    if (messages.length) return messages.join('\n')
  }
  return fallback
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof NetworkError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

type JsonBody = Record<string, unknown> | unknown[]

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: JsonBody | FormData
  query?: Record<string, string | number | boolean | null | undefined>
  signal?: AbortSignal
}

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const search = params.toString()
  return search ? `${path}?${search}` : path
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (MUTATING.has(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      body,
      credentials: 'same-origin',
      signal: options.signal,
    })
  } catch (error) {
    if (options.signal?.aborted && error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new NetworkError(error)
  }

  if (response.status === 204) return undefined as T
  let text: string
  try {
    text = await response.text()
  } catch (error) {
    if (options.signal?.aborted && error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ResponseError(error)
  }
  let data: unknown = undefined
  if (text) {
    try {
      data = JSON.parse(text)
    } catch (error) {
      if (response.ok) throw new ResponseError(error)
      data = text
    }
  }
  if (!response.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data
        ? (data as { detail: unknown }).detail
        : data
    throw new ApiError(
      response.status,
      detail,
      formatErrorDetail(detail, `Request failed (${response.status}).`),
    )
  }
  return data as T
}

export function isStatus(error: unknown, ...statuses: number[]): boolean {
  return error instanceof ApiError && statuses.includes(error.status)
}
