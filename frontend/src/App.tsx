import { useEffect, useState, type FormEvent } from 'react'
import './App.css'

type Channel = {
  channel_id: string
  title: string
  description: string
  subscriber_count: number
  video_count: number
  view_count: number
}

type Video = {
  youtube_video_id: string
  title: string
  description: string
  published_at: string
  thumbnail_url: string
}

type SyncResult = {
  fetched_count: number
  inserted_count: number
  updated_count: number
  total_stored_count: number
}

type DuplicateResult = {
  is_duplicate: boolean
  duplicate_type: 'exact_title' | 'similar_title' | 'similar_topic' | 'none'
  similarity_score: number
  matched_video_id: string | null
  matched_title: string | null
  reason: string
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

type Preferences = Record<string, unknown>

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const numberFormatter = new Intl.NumberFormat()

function App() {
  const [channel, setChannel] = useState<Channel | null>(null)
  const [message, setMessage] = useState(() => {
    const result = new URLSearchParams(window.location.search).get('youtube')
    if (result === 'connected') return 'Your YouTube channel is connected.'
    if (result === 'denied') return 'Google authorization was cancelled.'
    if (result === 'exchange_failed') {
      return `Google token exchange failed: ${new URLSearchParams(window.location.search).get('reason') ?? 'unknown error'}.`
    }
    if (result === 'failed') return 'Google authorization could not be completed.'
    return ''
  })
  const [loading, setLoading] = useState(true)
  const [videos, setVideos] = useState<Video[]>([])
  const [syncing, setSyncing] = useState(false)
  const [proposedTitle, setProposedTitle] = useState('')
  const [checkingDuplicate, setCheckingDuplicate] = useState(false)
  const [duplicateResult, setDuplicateResult] = useState<DuplicateResult | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [preferences, setPreferences] = useState<Preferences>({})
  const [sendingChat, setSendingChat] = useState(false)

  const loadChannel = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/youtube/channel`)
      if (response.status === 401) {
        setChannel(null)
        return
      }
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not load channel details.')
      setChannel(body)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load channel details.')
    } finally {
      setLoading(false)
    }
  }

  const loadVideos = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/youtube/videos`)
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not load stored videos.')
      setVideos(body.videos)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load stored videos.')
    }
  }

  const syncVideos = async () => {
    setSyncing(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/youtube/videos/sync`, { method: 'POST' })
      const body: SyncResult | { detail?: string } = await response.json()
      if (!response.ok) throw new Error('detail' in body ? body.detail : 'Could not sync videos.')
      const result = body as SyncResult
      setMessage(`Synced ${result.fetched_count} videos: ${result.inserted_count} added, ${result.updated_count} updated. ${result.total_stored_count} stored locally.`)
      await loadVideos()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not sync videos.')
    } finally {
      setSyncing(false)
    }
  }

  const checkDuplicate = async () => {
    if (!proposedTitle.trim()) {
      setDuplicateResult(null)
      setMessage('Enter a proposed title or topic first.')
      return
    }
    setCheckingDuplicate(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/check-duplicate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: proposedTitle }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not check for duplicates.')
      setDuplicateResult(body)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not check for duplicates.')
    } finally {
      setCheckingDuplicate(false)
    }
  }

  const loadChat = async () => {
    try {
      const [historyResponse, preferencesResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/chat/messages`),
        fetch(`${apiBaseUrl}/api/chat/preferences`),
      ])
      const historyBody = await historyResponse.json()
      const preferencesBody = await preferencesResponse.json()
      if (!historyResponse.ok || !preferencesResponse.ok) throw new Error('Could not load your saved planning preferences.')
      setChatMessages(historyBody.messages)
      setPreferences(preferencesBody.preferences)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not load chat preferences.')
    }
  }

  const sendChatMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!chatInput.trim()) return
    setSendingChat(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: chatInput }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not save your preference message.')
      setChatInput('')
      setPreferences(body.preferences)
      await loadChat()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not send your preference message.')
    } finally {
      setSendingChat(false)
    }
  }

  const resetChat = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/reset`, { method: 'POST' })
      if (!response.ok) throw new Error('Could not reset planning preferences.')
      setChatMessages([])
      setPreferences({})
      setChatInput('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not reset planning preferences.')
    }
  }

  const formatPreference = (value: unknown) => Array.isArray(value) ? value.join(', ') : String(value)

  useEffect(() => {
    const oauthResult = new URLSearchParams(window.location.search).get('youtube')
    if (oauthResult) window.history.replaceState({}, '', window.location.pathname)
    const loadTimer = window.setTimeout(() => { void Promise.all([loadChannel(), loadVideos(), loadChat()]) }, 0)
    return () => window.clearTimeout(loadTimer)
  }, [])

  return (
    <main className="app-shell">
      <section className="card" aria-labelledby="page-title">
        <p className="eyebrow">ShortsFlow AI</p>
        <h1 id="page-title">YouTube channel</h1>
        <p className="intro">Connect a Google account to view your channel’s current performance.</p>
        {message && <p className="message" role="status">{message}</p>}
        {!channel && !loading && <button className="connect-button" type="button" onClick={() => window.location.assign(`${apiBaseUrl}/api/youtube/connect`)}>Connect YouTube Channel</button>}
        {loading && <p className="muted">Checking your connection…</p>}
        {channel && (
          <div className="channel-details">
            <div className="channel-heading">
              <div><p className="connected-label">Connected channel</p><h2>{channel.title}</h2></div>
              <button className="secondary-button" type="button" onClick={() => window.location.assign(`${apiBaseUrl}/api/youtube/connect`)}>Reconnect</button>
            </div>
            {channel.description && <p className="description">{channel.description}</p>}
            <dl className="stats">
              <div><dt>Subscribers</dt><dd>{numberFormatter.format(channel.subscriber_count)}</dd></div>
              <div><dt>Videos</dt><dd>{numberFormatter.format(channel.video_count)}</dd></div>
              <div><dt>Views</dt><dd>{numberFormatter.format(channel.view_count)}</dd></div>
            </dl>
            <button className="connect-button sync-button" type="button" onClick={syncVideos} disabled={syncing}>
              {syncing ? 'Syncing Videos…' : 'Sync Videos'}
            </button>
          </div>
        )}

        <section className="chat-section" aria-labelledby="chat-heading">
          <div className="chat-heading">
            <div>
              <p className="connected-label">Shorts planner</p>
              <h2 id="chat-heading">Describe your Shorts</h2>
            </div>
            <button className="secondary-button" type="button" onClick={resetChat}>Reset</button>
          </div>
          <p className="muted">Tell us the category, format, style, and production preferences you want.</p>
          <div className="chat-layout">
            <div className="chat-panel" aria-live="polite">
              {chatMessages.length === 0 ? (
                <p className="muted">Start with something like: “I want CS Shorts with four options and no voiceover.”</p>
              ) : chatMessages.map((chatMessage, index) => (
                <p className={`chat-bubble ${chatMessage.role}`} key={`${chatMessage.created_at}-${index}`}>
                  {chatMessage.content}
                </p>
              ))}
            </div>
            <aside className="preferences-panel" aria-labelledby="preferences-heading">
              <h3 id="preferences-heading">Current preferences</h3>
              {Object.keys(preferences).length === 0 ? (
                <p className="muted">No preferences saved yet.</p>
              ) : (
                <dl>
                  {Object.entries(preferences).map(([key, value]) => (
                    <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{formatPreference(value)}</dd></div>
                  ))}
                </dl>
              )}
            </aside>
          </div>
          <form className="chat-form" onSubmit={sendChatMessage}>
            <label htmlFor="chat-input">Your Shorts requirements</label>
            <textarea
              id="chat-input"
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="e.g. CS and aptitude Shorts, 59 seconds, dark navy theme..."
              rows={3}
            />
            <button className="connect-button" type="submit" disabled={sendingChat}>
              {sendingChat ? 'Sending…' : 'Send'}
            </button>
          </form>
        </section>

        {channel && (
          <section className="duplicate-section" aria-labelledby="duplicate-heading">
            <h2 id="duplicate-heading">Duplicate check</h2>
            <p className="muted">Check a proposed video title or topic against your locally synced videos.</p>
            <div className="duplicate-form">
              <label htmlFor="proposed-title">Proposed title or topic</label>
              <input
                id="proposed-title"
                value={proposedTitle}
                onChange={(event) => setProposedTitle(event.target.value)}
                placeholder="e.g. BFS vs DFS explained"
              />
              <button className="connect-button" type="button" onClick={checkDuplicate} disabled={checkingDuplicate}>
                {checkingDuplicate ? 'Checking…' : 'Check Duplicate'}
              </button>
            </div>
            {duplicateResult && (
              <div className={`duplicate-result ${duplicateResult.is_duplicate ? 'duplicate-found' : 'duplicate-safe'}`}>
                <strong>
                  {duplicateResult.duplicate_type === 'exact_title' && 'Exact duplicate'}
                  {duplicateResult.duplicate_type === 'similar_title' && 'Similar title'}
                  {duplicateResult.duplicate_type === 'similar_topic' && 'Similar topic'}
                  {duplicateResult.duplicate_type === 'none' && 'Safe / New'}
                </strong>
                <p>{duplicateResult.reason}</p>
                {duplicateResult.is_duplicate && (
                  <p>Matched: <em>{duplicateResult.matched_title}</em> · {Math.round(duplicateResult.similarity_score * 100)}% similar</p>
                )}
              </div>
            )}
          </section>
        )}

        {channel && (
          <section className="video-section" aria-labelledby="videos-heading">
            <div className="video-section-heading">
              <h2 id="videos-heading">Stored videos</h2>
              <span>{videos.length} local</span>
            </div>
            {videos.length === 0 ? (
              <p className="muted">Sync your channel to save its uploaded videos locally.</p>
            ) : (
              <div className="video-list">
                {videos.map((video) => (
                  <article className="video-row" key={video.youtube_video_id}>
                    {video.thumbnail_url && <img src={video.thumbnail_url} alt="" />}
                    <div><h3>{video.title}</h3><p>{new Date(video.published_at).toLocaleDateString()}</p></div>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}
      </section>
    </main>
  )
}

export default App
