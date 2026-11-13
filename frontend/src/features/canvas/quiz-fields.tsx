import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { useStaff } from '@/features/admin/use-staff'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { canvasQuizzesQuery, refreshCanvasQuizzes } from './api'

interface Props {
  assignmentId: string
  onAssignmentId: (id: string) => void
  minimumScore: string
  onMinimumScore: (score: string) => void
}
export function CanvasQuizFields(props: Props) {
  const { user, can, keys } = useStaff()
  const client = useQueryClient()
  const quizzes = useQuery({
    ...canvasQuizzesQuery(user?.id ?? 'anonymous'),
    enabled: can('canvas.read'),
  })
  const refresh = useMutation({
    mutationFn: refreshCanvasQuizzes,
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.topic('canvas') })
    },
  })
  const known = quizzes.data?.items.some((quiz) => quiz.id === props.assignmentId)
  return (
    <div className="flex flex-col gap-4">
      <Field>
        <FieldLabel htmlFor="training-canvas-quiz">Canvas quiz</FieldLabel>
        <NativeSelect
          className="w-full max-w-full"
          id="training-canvas-quiz"
          value={props.assignmentId}
          onChange={(event) => props.onAssignmentId(event.target.value)}
          disabled={!can('canvas.read') || quizzes.isPending || quizzes.isError}
        >
          <NativeSelectOption value="">No Canvas quiz</NativeSelectOption>
          {props.assignmentId && !known ? (
            <NativeSelectOption value={props.assignmentId}>
              Currently selected quiz (not in cache)
            </NativeSelectOption>
          ) : null}
          {quizzes.data?.items.map((quiz) => (
            <NativeSelectOption key={quiz.id} value={quiz.id}>
              {quiz.title}
              {quiz.points_possible === null ? '' : ` (${quiz.points_possible} points)`}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <FieldDescription>Cached course quizzes.</FieldDescription>
        {quizzes.data ? (
          <FieldDescription>
            Quiz choices last refreshed: {formatDateTime(quizzes.data.refreshed_at)}.
          </FieldDescription>
        ) : null}
        {!can('canvas.read') ? (
          <FieldDescription>Canvas read permission is needed to choose a quiz.</FieldDescription>
        ) : null}
        {quizzes.isError ? <FieldError>{errorMessage(quizzes.error)}</FieldError> : null}
        {can('canvas.write') ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="self-start"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            Refresh quiz choices
          </Button>
        ) : null}
        {refresh.data ? (
          <FieldDescription role="status">{refresh.data.message}</FieldDescription>
        ) : null}
        {refresh.isError ? <FieldError>{errorMessage(refresh.error)}</FieldError> : null}
      </Field>
      {props.assignmentId ? (
        <div className="flex flex-col gap-4">
          <Field>
            <FieldLabel htmlFor="training-canvas-score">Minimum passing score</FieldLabel>
            <Input
              id="training-canvas-score"
              type="number"
              min="0"
              step="any"
              value={props.minimumScore}
              onChange={(event) => props.onMinimumScore(event.target.value)}
              placeholder="Any graded score"
            />
            <FieldDescription>
              Points, not percent. Leave blank to accept any graded result.
            </FieldDescription>
          </Field>
        </div>
      ) : null}
    </div>
  )
}
