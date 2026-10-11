import { useEffect, useState, type FormEvent } from 'react'
import './App.css'
import { AppShell } from './components/AppShell'
import { HomePage } from './pages/HomePage'
import { ChatPage } from './pages/ChatPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { SettingsPage } from './pages/SettingsPage'
import type { AppRoute, AssistantMessage, Channel, DuplicateResult, Preferences, SyncResult, Video } from './types'

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const routeForPath = (path: string): AppRoute => {
  const route = path === '/' ? '/home' : path
  return ['/home', '/chat', '/images', '/video', '/uploads', '/profile'].includes(route) ? route as AppRoute : '/home'
}

function App() {
  const [route, setRoute] = useState<AppRoute>(() => routeForPath(window.location.pathname))
  const [channel, setChannel] = useState<Channel | null>(null)
  const [message, setMessage] = useState(() => {
    const result = new URLSearchParams(window.location.search).get('youtube')
    if (result === 'connected') return 'Your YouTube channel is connected.'
    if (result === 'denied') return 'Google authorization was cancelled.'
    return result ? 'Google authorization could not be completed.' : ''
  })
  const [loading, setLoading] = useState(true)
  const [videos, setVideos] = useState<Video[]>([])
  const [syncing, setSyncing] = useState(false)
  const [proposedTitle, setProposedTitle] = useState('')
  const [checkingDuplicate, setCheckingDuplicate] = useState(false)
  const [duplicateResult, setDuplicateResult] = useState<DuplicateResult | null>(null)
  const [preferences, setPreferences] = useState<Preferences>({})
  const [assistantMessages, setAssistantMessages] = useState<AssistantMessage[]>([])
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantSessionId, setAssistantSessionId] = useState(() => localStorage.getItem('shortsflow-assistant-session') ?? '')
  const [assistantSending, setAssistantSending] = useState(false)
  const [draftCount, setDraftCount] = useState(0)

  const navigate = (nextRoute: AppRoute) => {
    const target = nextRoute === '/home' ? '/home' : nextRoute
    window.history.pushState({}, '', target)
    setRoute(nextRoute)
  }

  const loadChannel = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/youtube/channel`)
      if (response.status === 401) { setChannel(null); return }
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not load channel details.')
      setChannel(body)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load channel details.') } finally { setLoading(false) }
  }

  const loadVideos = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/youtube/videos`)
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not load stored videos.')
      setVideos(body.videos)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load stored videos.') }
  }

  const loadSettings = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/settings`)
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not load saved Settings.')
      setPreferences(body.preferences)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load saved Settings.') }
  }

  const loadDrafts = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/content/drafts`)
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not load generated drafts.')
      setDraftCount(Array.isArray(body.drafts) ? body.drafts.length : 0)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load generated drafts.') }
  }

  const syncVideos = async () => {
    setSyncing(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/youtube/videos/sync`, { method: 'POST' })
      const body: SyncResult | { detail?: string } = await response.json()
      if (!response.ok) throw new Error('detail' in body ? body.detail : 'Could not sync videos.')
      const result = body as SyncResult
      setMessage(`Synced ${result.fetched_count} videos: ${result.inserted_count} added, ${result.updated_count} updated.`)
      await loadVideos()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not sync videos.') } finally { setSyncing(false) }
  }

  const checkDuplicate = async () => {
    if (!proposedTitle.trim()) { setMessage('Enter a proposed title or topic first.'); return }
    setCheckingDuplicate(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/videos/check-duplicate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: proposedTitle }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not check for duplicates.')
      setDuplicateResult(body)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not check for duplicates.') } finally { setCheckingDuplicate(false) }
  }

  const sendAssistantMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const messageText = assistantInput.trim()
    if (!messageText) return
    setAssistantSending(true)
    setAssistantMessages((current) => [...current, { role: 'user', content: messageText }])
    setAssistantInput('')
    try {
      const response = await fetch(`${apiBaseUrl}/api/assistant/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: messageText, session_id: assistantSessionId || null }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not reach the assistant.')
      setAssistantSessionId(body.session_id)
      localStorage.setItem('shortsflow-assistant-session', body.session_id)
      setAssistantMessages((current) => [...current, { role: 'assistant', content: body.response, tools_used: body.tools_used ?? [] }])
    } catch (error) { setAssistantMessages((current) => [...current, { role: 'assistant', content: error instanceof Error ? error.message : 'Could not reach the assistant.' }]) } finally { setAssistantSending(false) }
  }

  const clearAssistantConversation = async () => {
    try {
      if (assistantSessionId) await fetch(`${apiBaseUrl}/api/assistant/conversations/${assistantSessionId}/clear`, { method: 'POST' })
      localStorage.removeItem('shortsflow-assistant-session')
      setAssistantSessionId(''); setAssistantMessages([]); setAssistantInput('')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not clear the assistant conversation.') }
  }

  const saveSettings = async (nextPreferences: Preferences) => {
    const response = await fetch(`${apiBaseUrl}/api/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preferences: nextPreferences }) })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail ?? 'Could not save Settings.')
    setPreferences(body.preferences)
  }

  useEffect(() => {
    const oauthResult = new URLSearchParams(window.location.search).get('youtube')
    if (oauthResult) window.history.replaceState({}, '', window.location.pathname)
    const onPopState = () => setRoute(routeForPath(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    const loadTimer = window.setTimeout(() => { void Promise.all([loadChannel(), loadVideos(), loadSettings(), loadDrafts()]) }, 0)
    return () => { window.removeEventListener('popstate', onPopState); window.clearTimeout(loadTimer) }
  }, [])

  const content = route === '/chat' ? <ChatPage messages={assistantMessages} chatInput={assistantInput} sending={assistantSending} onChatInputChange={setAssistantInput} onSend={sendAssistantMessage} onClear={clearAssistantConversation} />
    : route === '/images' ? <PlaceholderPage eyebrow="Scene workspace" title="Images" description="Prepare visual scenes for every moment of a Short." items={['Question scene', 'Options scene', 'Answer reveal', '9:16 preview']} />
      : route === '/video' ? <PlaceholderPage eyebrow="Production workspace" title="Video Editing" description="Shape scenes, timing, transitions, and the final Short." items={['Scene timeline', 'Timer and transitions', 'Music and voiceover', 'Preview validation']} />
        : route === '/uploads' ? <PlaceholderPage eyebrow="Publishing workspace" title="Uploads" description="Keep every finished Short organized before it goes live." items={['Ready to publish', 'Scheduled', 'Published', 'Failed and retry']} />
          : route === '/profile' ? <SettingsPage channel={channel} preferences={preferences} onReconnect={() => window.location.assign(`${apiBaseUrl}/api/youtube/connect`)} onSave={saveSettings} />
            : <HomePage channel={channel} loading={loading} videos={videos} draftCount={draftCount} syncing={syncing} duplicateResult={duplicateResult} proposedTitle={proposedTitle} onProposedTitleChange={setProposedTitle} onConnect={() => window.location.assign(`${apiBaseUrl}/api/youtube/connect`)} onSync={syncVideos} onCheckDuplicate={checkDuplicate} checkingDuplicate={checkingDuplicate} />

  return <AppShell activeRoute={route} onNavigate={navigate}>{message && <div className="global-message" role="status">{message}</div>}{content}</AppShell>
}

export default App
