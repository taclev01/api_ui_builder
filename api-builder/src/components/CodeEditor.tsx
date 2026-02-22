import { useEffect, useRef } from 'react';
import { basicSetup, EditorView } from 'codemirror';

export type CodeEditorProps = {
  value: string;
  onChange: (nextValue: string) => void;
};

export function CodeEditor({ value, onChange }: CodeEditorProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);

  useEffect(() => {
    if (!rootRef.current) {
      return;
    }

    const view = new EditorView({
      doc: value,
      extensions: [
        basicSetup,
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChange(update.state.doc.toString());
          }
        }),
      ],
      parent: rootRef.current,
    });

    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [onChange]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) {
      return;
    }

    const current = view.state.doc.toString();
    if (current === value) {
      return;
    }

    view.dispatch({
      changes: { from: 0, to: current.length, insert: value },
    });
  }, [value]);

  return <div className="code-editor" ref={rootRef} />;
}
