import type { FormEvent } from 'react'
import type { AssistantMessage } from '../types'

type ChatPageProps = {
  messages: AssistantMessage[]
  chatInput: string
  sending: boolean
  onChatInputChange: (value: string) => void
  onSend: (event: FormEvent<HTMLFormElement>) => void
  onClear: () => void
}

const starterQuestions = ['How many videos are on my channel?', 'What are my current settings?', 'What is my latest generated draft?', 'Help me plan today’s Shorts.']

export function ChatPage({ messages, chatInput, sending, onChatInputChange, onSend, onClear }: ChatPageProps) {
  return <section className="page-stack assistant-page">
    <header className="page-header"><p className="eyebrow">ShortsFlow assistant</p><h1>Your workspace, in conversation.</h1><p>Ask about your channel, videos, drafts, Settings, and daily workflow. The assistant reads ShortsFlow data but never changes it.</p></header>
    <section className="surface-card assistant-card"><div className="section-heading"><div><p className="eyebrow">Local AI · Ollama</p><h2>Ask ShortsFlow</h2></div><button className="button button-secondary" type="button" onClick={onClear}>New conversation</button></div><div className="assistant-chat" aria-live="polite">{messages.length === 0 ? <div className="assistant-empty"><h3>How can I help with your Shorts today?</h3><p>I can check your uploaded videos, saved defaults, generated drafts, duplicate risk, and upload slots.</p><div className="starter-questions">{starterQuestions.map((question) => <button type="button" key={question} onClick={() => onChatInputChange(question)}>{question}</button>)}</div></div> : messages.map((message, index) => <article className={`chat-bubble ${message.role}`} key={`${message.role}-${index}`}><p>{message.content}</p>{message.role === 'assistant' && message.tools_used && message.tools_used.length > 0 && <span className="tool-indicator">Used: {message.tools_used.map((tool) => tool.replaceAll('_', ' ')).join(' · ')}</span>}</article>)}{sending && <article className="chat-bubble assistant typing"><p>Checking your ShortsFlow workspace…</p></article>}</div><form className="chat-form assistant-form" onSubmit={onSend}><label className="field-label" htmlFor="assistant-input">Ask about your workspace</label><textarea id="assistant-input" value={chatInput} onChange={(event) => onChatInputChange(event.target.value)} placeholder="e.g. Have I already made a video about binary search?" rows={3} /><button className="button" type="submit" disabled={sending}>{sending ? 'Thinking…' : 'Send message'}</button></form></section>
  </section>
}
