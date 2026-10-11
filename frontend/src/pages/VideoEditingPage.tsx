import { useCallback, useEffect, useState } from 'react'
import type { GeneratedDraft, GeneratedScene, RenderedVideo } from '../types'

export function VideoEditingPage({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [drafts, setDrafts] = useState<GeneratedDraft[]>([])
  const [draftId, setDraftId] = useState<number | null>(null)
  const [scenes, setScenes] = useState<GeneratedScene[]>([])
  const [video, setVideo] = useState<RenderedVideo | null>(null)
  const [status, setStatus] = useState('')
  const [working, setWorking] = useState(false)

  const load = useCallback(async (id: number) => {
    const response = await fetch(`${apiBaseUrl}/api/video-rendering/${id}`)
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail ?? 'Could not load video workspace.')
    setScenes(body.scenes); setVideo(body.video)
  }, [apiBaseUrl])

  useEffect(() => { void (async () => { try { const response = await fetch(`${apiBaseUrl}/api/content/drafts`); const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? 'Could not load drafts.'); const next = body.drafts as GeneratedDraft[]; setDrafts(next); if (next[0]) { setDraftId(next[0].id); await load(next[0].id) } } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not load video workspace.') } })() }, [apiBaseUrl, load])

  const render = async (rerender = false) => {
    if (!draftId) return
    setWorking(true); setStatus(reRenderLabel(rerender))
    try { const url = rerender ? `${apiBaseUrl}/api/video-rendering/${draftId}/rerender` : `${apiBaseUrl}/api/video-rendering/render`; const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: rerender ? undefined : JSON.stringify({ draft_id: draftId }) }); const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? 'Could not render video.'); setVideo(body.video); await load(draftId); setStatus('Video rendered. Run validation to confirm the final MP4.') } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not render video.') } finally { setWorking(false) }
  }

  const validate = async () => {
    if (!draftId) return
    setWorking(true)
    try { const response = await fetch(`${apiBaseUrl}/api/video-rendering/${draftId}/validate`, { method: 'POST' }); const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? 'Could not validate video.'); setVideo(body.video); setStatus(body.valid ? 'Video passed validation.' : body.errors.join(' ')) } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not validate video.') } finally { setWorking(false) }
  }

  const changeDraft = async (value: string) => { const id = Number(value); setDraftId(id); setVideo(null); setScenes([]); setStatus(''); try { await load(id) } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not load draft.') } }
  const total = video?.timeline?.reduce((sum, item) => sum + Number(item.duration_seconds), 0) ?? 0

  return <><header className="page-header"><p className="eyebrow">Production workspace</p><h1>Render a polished Short locally.</h1><p>Validated scene images become one precise 9:16 MP4. Your source images stay intact when re-rendering.</p></header><section className="surface-card video-controls"><label className="field-label" htmlFor="render-draft">Accepted draft<select id="render-draft" value={draftId ?? ''} onChange={(event) => void changeDraft(event.target.value)}>{drafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.title}</option>)}</select></label><div className="image-actions"><button className="button" disabled={!draftId || working} onClick={() => void render()}>{working ? 'Rendering…' : 'Render video'}</button><button className="button button-secondary" disabled={!video || working} onClick={() => void validate()}>Validate video</button><button className="button button-secondary" disabled={!video || working} onClick={() => void render(true)}>Re-render</button></div></section>{status && <div className="global-message" role="status">{status}</div>}<section className="video-workspace"><article className="surface-card"><p className="eyebrow">Scene timeline</p><h2>{scenes.length} validated scenes · {total ? `${total.toFixed(3)} seconds` : 'render to calculate duration'}</h2><div className="timeline-list">{(video?.timeline ?? scenes.map((scene) => ({ ...scene, duration_seconds: 0 }))).map((item, index) => <div key={item.scene_id} className="timeline-item"><strong>{index + 1}</strong><span>{item.scene_type}</span><small>{Number(item.duration_seconds) ? `${Number(item.duration_seconds).toFixed(3)} sec` : 'awaiting render'}</small></div>)}</div></article><article className="surface-card video-preview"><p className="eyebrow">Final preview</p>{video?.video_path ? <video controls src={`${apiBaseUrl}${video.video_path}`} /> : <div className="video-empty">Render the validated scenes to preview your Short.</div>}<h2>{video?.validation_status === 'valid' ? 'Validated MP4' : 'Ready for validation'}</h2>{video && <p className="muted">{video.width} × {video.height} · {video.duration_seconds?.toFixed(3)} sec · {formatSize(video.file_size_bytes)}<br />{video.audio_note}</p>}</article></section></>
}

const reRenderLabel = (rerender: boolean) => rerender ? 'Re-rendering from existing validated scenes…' : 'Rendering your Short locally…'
const formatSize = (bytes?: number | null) => bytes ? `${(bytes / 1024 / 1024).toFixed(2)} MB` : 'size pending'
