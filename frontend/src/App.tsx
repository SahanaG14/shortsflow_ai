import { useEffect, useState, type FormEvent } from 'react'
import './App.css'
import { AppShell } from './components/AppShell'
import { HomePage } from './pages/HomePage'
import { ChatPage } from './pages/ChatPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { SettingsPage } from './pages/SettingsPage'
import type { AppRoute, Channel, ChatMessage, DuplicateCheckHistory, DuplicateResult, GeneratedDraft, Preferences, SyncResult, Video } from './types'

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
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [preferences, setPreferences] = useState<Preferences>({})
  const [draftOverrides, setDraftOverrides] = useState<Preferences>({})
  const [sendingChat, setSendingChat] = useState(false)
  const [generatingDraft, setGeneratingDraft] = useState(false)
  const [generatedDraft, setGeneratedDraft] = useState<GeneratedDraft | null>(null)
  const [generationChecks, setGenerationChecks] = useState<DuplicateCheckHistory[]>([])
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

  const loadChat = async () => {
    try {
      const [historyResponse, preferencesResponse] = await Promise.all([fetch(`${apiBaseUrl}/api/chat/messages`), fetch(`${apiBaseUrl}/api/chat/preferences`)])
      const historyBody = await historyResponse.json()
      const preferencesBody = await preferencesResponse.json()
      if (!historyResponse.ok || !preferencesResponse.ok) throw new Error('Could not load your saved planning preferences.')
      setChatMessages(historyBody.messages)
      setPreferences(preferencesBody.preferences)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not load chat preferences.') }
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

  const sendChatMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!chatInput.trim()) return
    setSendingChat(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: chatInput }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not save your draft instruction.')
      setChatInput('')
      setDraftOverrides((current) => ({ ...current, ...(body.overrides ?? {}) }))
      await loadChat()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not send your draft instruction.') } finally { setSendingChat(false) }
  }

  const resetChat = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/reset`, { method: 'POST' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not reset chat context.')
      setChatMessages([]); setPreferences(body.preferences ?? preferences); setDraftOverrides({}); setChatInput('')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not reset chat context.') }
  }

  const generateDraft = async () => {
    setGeneratingDraft(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/content/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ max_attempts: 5, temporary_overrides: draftOverrides }) })
      const body = await response.json()
      setGenerationChecks(body.duplicate_checks ?? [])
      if (!response.ok || !body.accepted) throw new Error(body.detail ?? 'No non-duplicate draft could be generated.')
      setGeneratedDraft(body.draft)
      setDraftOverrides({})
      await loadDrafts()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not generate a Short draft.') } finally { setGeneratingDraft(false) }
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
    const loadTimer = window.setTimeout(() => { void Promise.all([loadChannel(), loadVideos(), loadChat(), loadDrafts()]) }, 0)
    return () => { window.removeEventListener('popstate', onPopState); window.clearTimeout(loadTimer) }
  }, [])

  const content = route === '/chat' ? <ChatPage messages={chatMessages} preferences={preferences} draftOverrides={draftOverrides} chatInput={chatInput} sending={sendingChat} onChatInputChange={setChatInput} onSend={sendChatMessage} onReset={resetChat} generating={generatingDraft} onGenerate={generateDraft} draft={generatedDraft} checks={generationChecks} />
    : route === '/images' ? <PlaceholderPage eyebrow="Scene workspace" title="Images" description="Prepare visual scenes for every moment of a Short." items={['Question scene', 'Options scene', 'Answer reveal', '9:16 preview']} />
      : route === '/video' ? <PlaceholderPage eyebrow="Production workspace" title="Video Editing" description="Shape scenes, timing, transitions, and the final Short." items={['Scene timeline', 'Timer and transitions', 'Music and voiceover', 'Preview validation']} />
        : route === '/uploads' ? <PlaceholderPage eyebrow="Publishing workspace" title="Uploads" description="Keep every finished Short organized before it goes live." items={['Ready to publish', 'Scheduled', 'Published', 'Failed and retry']} />
          : route === '/profile' ? <SettingsPage channel={channel} preferences={preferences} onReconnect={() => window.location.assign(`${apiBaseUrl}/api/youtube/connect`)} onSave={saveSettings} />
            : <HomePage channel={channel} loading={loading} videos={videos} draftCount={draftCount} syncing={syncing} duplicateResult={duplicateResult} proposedTitle={proposedTitle} onProposedTitleChange={setProposedTitle} onConnect={() => window.location.assign(`${apiBaseUrl}/api/youtube/connect`)} onSync={syncVideos} onCheckDuplicate={checkDuplicate} checkingDuplicate={checkingDuplicate} />

  return <AppShell activeRoute={route} onNavigate={navigate}>{message && <div className="global-message" role="status">{message}</div>}{content}</AppShell>
}

export default App
