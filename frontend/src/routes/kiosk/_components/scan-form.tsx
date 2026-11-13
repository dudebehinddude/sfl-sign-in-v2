import { useState, type Ref } from 'react'
import { ScanLineIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Spinner } from '@/components/ui/spinner'
import { normalizeIdentifier } from '@/features/kiosk/machine'
import { SCAN_INPUT_ATTR } from '@/features/kiosk/scanner-burst'

interface ScanFormProps {
  id: string
  label: string
  placeholder: string
  compact?: boolean
  busy?: boolean
  inputRef?: Ref<HTMLInputElement>
  autoFocus?: boolean
  description?: string
  onScan: (identifier: string) => void
}

export function ScanForm({
  id,
  label,
  placeholder,
  busy,
  compact = false,
  inputRef,
  autoFocus,
  description,
  onScan,
}: ScanFormProps) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (busy) return
        const identifier = normalizeIdentifier(value)
        setValue('')
        if (!identifier) {
          setError(
            value.trim()
              ? 'That is not a valid card number. Scan again or type your nine-digit ID.'
              : null,
          )
          return
        }
        setError(null)
        onScan(identifier)
      }}
    >
      <Field className="gap-2" data-invalid={error ? true : undefined}>
        <FieldLabel htmlFor={id} className={compact ? 'sr-only' : undefined}>{label}</FieldLabel>
        <div className="flex min-w-0 gap-2">
          <InputGroup className={compact ? 'h-11 min-w-0 flex-1' : 'h-14 min-w-0 flex-1'}>
            {compact ? busy ? <InputGroupAddon><Spinner /></InputGroupAddon> : null : <InputGroupAddon>{busy ? <Spinner /> : <ScanLineIcon />}</InputGroupAddon>}
            <InputGroupInput
              id={id}
              ref={inputRef}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder={placeholder}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              inputMode="numeric"
              autoFocus={autoFocus}
              maxLength={64}
              readOnly={busy}
              aria-busy={busy}
              aria-invalid={error ? true : undefined}
              className={compact ? 'min-h-11 min-w-0 text-base' : 'min-h-11 min-w-0 text-xl'}
              {...{ [SCAN_INPUT_ATTR]: '' }}
            />
          </InputGroup>
          <Button type="submit" tabIndex={compact ? -1 : undefined} className={compact ? 'sr-only' : 'min-h-14 shrink-0 px-4'} disabled={busy}>
            Continue
          </Button>
        </div>
        {error ? (
          <FieldError>{error}</FieldError>
        ) : description ? (
          <FieldDescription>{description}</FieldDescription>
        ) : null}
      </Field>
    </form>
  )
}
