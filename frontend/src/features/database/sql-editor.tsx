import { Editor, loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor/editor/editor.api'
// oxlint-disable-next-line import/no-unassigned-import -- Monaco registers SQL through this side-effect module.
import 'monaco-editor/languages/definitions/sql/register'
// oxlint-disable-next-line import/default -- Vite supplies the default worker constructor for ?worker imports.
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'
import { useTheme } from 'next-themes'
import { useEffect, useRef } from 'react'
import type { DatabaseTable } from './data'

;(globalThis as typeof globalThis & { MonacoEnvironment: monaco.Environment }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
}
loader.config({ monaco })

export default function SqlEditor({ value, onChange, tables, disabled, onRun }: {
  value: string
  onChange: (value: string) => void
  tables: DatabaseTable[]
  disabled: boolean
  onRun?: (sql: string) => void
}) {
  const { resolvedTheme } = useTheme()
  const run = useRef(onRun)
  useEffect(() => { run.current = onRun }, [onRun])
  useEffect(() => {
    const provider = monaco.languages.registerCompletionItemProvider('sql', {
      triggerCharacters: ['.'],
      provideCompletionItems(model, position) {
        const word = model.getWordUntilPosition(position)
        const range = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn)
        return {
          suggestions: tables.flatMap(table => [
            { label: table.name, insertText: `"${table.schema}"."${table.name}"`, kind: monaco.languages.CompletionItemKind.Class, range },
            ...table.columns.map(column => ({
              label: column.name,
              insertText: `"${column.name}"`,
              detail: `${table.name} · ${column.type}`,
              kind: monaco.languages.CompletionItemKind.Field,
              range,
            })),
          ]),
        }
      },
    })
    return () => provider.dispose()
  }, [tables])
  return (
    <div className="min-w-0 overflow-hidden rounded-md border" aria-label="SQL editor">
      <Editor
        height="260px"
        language="sql"
        value={value}
        onChange={next => onChange(next ?? '')}
        theme={resolvedTheme === 'dark' ? 'vs-dark' : 'vs'}
        keepCurrentModel={false}
        onMount={editor => {
          editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => run.current?.(editor.getValue()))
        }}
        options={{
          ariaLabel: 'SQL query',
          readOnly: disabled,
          automaticLayout: true,
          minimap: { enabled: false },
          fontSize: 13,
          tabSize: 2,
          scrollBeyondLastLine: false,
          wordWrap: 'off',
          padding: { top: 10, bottom: 10 },
        }}
      />
    </div>
  )
}
