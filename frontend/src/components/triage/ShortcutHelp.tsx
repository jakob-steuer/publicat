const SHORTCUTS: Array<[string, string]> = [
  ['j / ↓', 'Next paper'],
  ['k / ↑', 'Previous paper'],
  ['Enter / Space', 'Open or close the reading pane'],
  ['s', 'Star (save, +2)'],
  ['u', 'Upvote (relevant, +1)'],
  ['n', 'Neutral (mark read, 0)'],
  ['d', 'Downvote (discard, -1)'],
  ['z', 'Undo last vote'],
  ['o', 'Open the article in a new tab'],
  ['x', 'Select / deselect for bulk actions'],
  ['/', 'Focus search'],
  ['?', 'This help'],
  ['Esc', 'Close pane / help'],
]

export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">Keyboard shortcuts</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          {SHORTCUTS.map(([key, desc]) => (
            <div key={key} className="contents">
              <dt><kbd className="px-1.5 py-0.5 rounded border border-border bg-muted font-mono text-xs">{key}</kbd></dt>
              <dd className="text-foreground/80">{desc}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-muted-foreground mt-4">After a vote the focus moves to the next paper, so a daily pass is just s / u / n / d.</p>
      </div>
    </div>
  )
}
