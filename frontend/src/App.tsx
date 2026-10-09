import { useEffect, useState } from 'react'
import './App.css'

type Channel = {
  channel_id: string
  title: string
  description: string
  subscriber_count: number
  video_count: number
  view_count: number
}

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

  useEffect(() => {
    const oauthResult = new URLSearchParams(window.location.search).get('youtube')
    if (oauthResult) window.history.replaceState({}, '', window.location.pathname)
    const loadTimer = window.setTimeout(() => { void loadChannel() }, 0)
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
          </div>
        )}
      </section>
    </main>
  )
}

export default App
