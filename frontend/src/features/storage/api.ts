import { queryOptions } from '@tanstack/react-query'
import { api, ApiError, buildUrl, NetworkError, ResponseError } from '@/lib/api/client'
import { staffKeys } from '@/lib/query-keys'

export const STORAGE_UPLOAD_BYTES = 5 * 1024 * 1024
export interface StorageUser {
  id: string
  display_name: string
  href: string
}
export interface StorageObject {
  key: string
  size: number
  last_modified: string | null
  etag: string | null
  users: StorageUser[]
}
export interface StoragePage {
  items: StorageObject[]
  prefix: string
  next_cursor: string | null
  limit: number
  upload_max_bytes: number
}
export function storageQuery(
  principalId: string,
  prefix: string,
  cursor: string | null,
  limit: number,
) {
  return queryOptions({
    queryKey: staffKeys(principalId).topic('storage', prefix, cursor, limit),
    queryFn: ({ signal }) =>
      api<StoragePage>('/api/admin/storage/objects', { query: { prefix, cursor, limit }, signal }),
  })
}

export function deleteObject(key: string) {
  return api<void>('/api/admin/storage/object', { method: 'DELETE', query: { key } })
}
export function canPreviewObject(object: Pick<StorageObject, 'key' | 'size'>): boolean {
  return /\.(png|jpe?g)$/i.test(object.key) && object.size <= STORAGE_UPLOAD_BYTES
}

export function storagePreviewUrl(key: string, size: 128 | 1024 = 1024) {
  return buildUrl('/api/admin/storage/preview', { key, size })
}

export function storageDownloadUrl(key: string) {
  return buildUrl('/api/admin/storage/object', { key })
}

export async function downloadObject(key: string): Promise<void> {
  let response: Response
  try {
    response = await fetch(storageDownloadUrl(key), { credentials: 'same-origin' })
  } catch (error) {
    throw new NetworkError(error)
  }
  if (!response.ok) {
    let detail: unknown = null
    try {
      detail = (await response.json()).detail
    } catch {
      /* Keep an HTTP error readable if its body is interrupted. */
    }
    throw new ApiError(
      response.status,
      detail,
      typeof detail === 'string' ? detail : 'The file could not be downloaded.',
    )
  }
  let blob: Blob
  try {
    blob = await response.blob()
  } catch (error) {
    throw new ResponseError(error)
  }
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = key.split('/').at(-1) || 'download'
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

export function storageConflict(error: unknown): { message: string; users: StorageUser[] } | null {
  if (
    !(error instanceof ApiError) ||
    error.status !== 409 ||
    !error.detail ||
    typeof error.detail !== 'object'
  )
    return null
  const detail = error.detail as { message?: unknown; users?: unknown }
  if (typeof detail.message !== 'string') return null
  const users = Array.isArray(detail.users)
    ? detail.users.filter(
        (value): value is StorageUser =>
          !!value &&
          typeof value === 'object' &&
          typeof value.id === 'string' &&
          typeof value.display_name === 'string' &&
          typeof value.href === 'string' &&
          /^\/admin\/users\/[a-f0-9-]+$/i.test(value.href),
      )
    : []
  return { message: detail.message, users }
}

export function formatStorageSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
