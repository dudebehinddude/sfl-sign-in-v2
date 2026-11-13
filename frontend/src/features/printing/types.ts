export interface PrintResult {
  status: 'sent' | 'offline' | 'busy'
  label_id?: string
  message: string
}
export interface PrintingStatus {
  connected: boolean
  busy: boolean
  last_result: null | {
    status: 'printed' | 'failed' | 'unknown'
    label_id: string
    display_name: string
    at: string
    message?: string
  }
}
