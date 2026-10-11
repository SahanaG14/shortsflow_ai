import type { FormEvent } from 'react'
import type { ChatMessage, DuplicateCheckHistory, GeneratedDraft, Preferences } from '../types'

type ChatPageProps = {
  messages: ChatMessage[]
  preferences: Preferences
  draftOverrides: Preferences
  chatInput: string
  sending: boolean
  onChatInputChange: (value: string) => void
  onSend: (event: FormEvent<HTMLFormElement>) => void
  onReset: () => void
  generating: boolean
  onGenerate: () => void
  draft: GeneratedDraft | null
  checks: DuplicateCheckHistory[]
}

const formatPreference = (value: unknown) => Array.isArray(value) ? value.join(', ') : String(value)

export function ChatPage({ messages, preferences, draftOverrides, chatInput, sending, onChatInputChange, onSend, onReset, generating, onGenerate, draft, checks }: ChatPageProps) {
  return <section className="page-stack">
    <header className="page-header"><p className="eyebrow">Creative workspace</p><h1>Plan your next Short.</h1><p>Chat starts from your saved Settings. Instructions here apply only to the current draft.</p></header>
    <div className="chat-workspace">
      <section className="surface-card chat-card"><div className="section-heading"><div><p className="eyebrow">Shorts planner</p><h2>Conversation</h2></div><button className="button button-secondary" type="button" onClick={onReset}>New draft</button></div><div className="chat-panel" aria-live="polite">{messages.length === 0 ? <p className="muted">Add a temporary instruction for this draft, such as “use a 10 second thinking timer.”</p> : messages.map((message, index) => <p className={`chat-bubble ${message.role}`} key={`${message.created_at}-${index}`}>{message.content}</p>)}</div><form className="chat-form" onSubmit={onSend}><label className="field-label" htmlFor="chat-input">Temporary draft instructions</label><textarea id="chat-input" value={chatInput} onChange={(event) => onChatInputChange(event.target.value)} placeholder="e.g. For this video, use a 10 second thinking timer." rows={4} /><button className="button" type="submit" disabled={sending}>{sending ? 'Adding…' : 'Add to draft'}</button></form></section>
      <aside className="surface-card preferences-card"><p className="eyebrow">Saved Settings</p><h2>Generation defaults</h2>{Object.keys(preferences).length === 0 ? <p className="muted">No settings saved yet.</p> : <dl>{Object.entries(preferences).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{formatPreference(value)}</dd></div>)}</dl>}<div className="draft-overrides"><p className="eyebrow">This draft only</p>{Object.keys(draftOverrides).length === 0 ? <p className="muted">No temporary overrides.</p> : <dl>{Object.entries(draftOverrides).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{formatPreference(value)}</dd></div>)}</dl>}</div></aside>
    </div>
    <section className="surface-card generation-card"><div className="section-heading"><div><p className="eyebrow">Content draft</p><h2>Generate a duplicate-safe Short</h2><p className="muted">Uses saved Settings plus the temporary overrides shown above, then checks the synced catalog.</p></div><button className="button" type="button" onClick={onGenerate} disabled={generating}>{generating ? 'Generating…' : 'Generate Short'}</button></div>{draft && <article className="draft-content"><p className="eyebrow">{draft.topic}</p><h3>{draft.title}</h3><p><strong>Hook</strong>{draft.hook}</p><p><strong>Question</strong>{draft.question}</p>{draft.options.length > 0 && <ol>{draft.options.map((option) => <li key={option}>{option}</li>)}</ol>}<p><strong>Answer</strong>{draft.correct_answer}</p>{draft.explanation && <p><strong>Explanation</strong>{draft.explanation}</p>}<p><strong>Scene script</strong>{draft.scene_script}</p><p><strong>Target duration</strong>{draft.target_duration_seconds} seconds</p></article>}{checks.length > 0 && <div className="result-banner success"><strong>Duplicate check {checks.at(-1)?.accepted ? 'passed' : 'rejected'}</strong><p>{checks.length} attempt{checks.length === 1 ? '' : 's'} · {checks.at(-1)?.reason}</p></div>}</section>
  </section>
}
