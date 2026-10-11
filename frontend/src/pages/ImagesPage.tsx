import { useCallback, useEffect, useState } from 'react'
import type { GeneratedDraft, GeneratedScene } from '../types'

type ImagesPageProps = { apiBaseUrl: string }

export function ImagesPage({ apiBaseUrl }: ImagesPageProps) {
  const [drafts, setDrafts] = useState<GeneratedDraft[]>([])
  const [draftId, setDraftId] = useState<number | null>(null)
  const [scenes, setScenes] = useState<GeneratedScene[]>([])
  const [status, setStatus] = useState('')
  const [working, setWorking] = useState(false)

  const loadScenes = useCallback(async (selectedId: number) => {
    const response = await fetch(`${apiBaseUrl}/api/images/scenes/${selectedId}`)
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail ?? 'Could not load scenes.')
    setScenes(body.scenes)
  }, [apiBaseUrl])

  useEffect(() => {
    void (async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/api/content/drafts`)
        const body = await response.json()
        if (!response.ok) throw new Error(body.detail ?? 'Could not load accepted drafts.')
        const nextDrafts = body.drafts as GeneratedDraft[]
        setDrafts(nextDrafts)
        if (nextDrafts[0]) { setDraftId(nextDrafts[0].id); await loadScenes(nextDrafts[0].id) }
      } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not load image workspace.') }
    })()
  }, [apiBaseUrl, loadScenes])

  const selectDraft = async (value: string) => {
    const nextId = Number(value)
    setDraftId(nextId); setStatus(''); setScenes([])
    try { await loadScenes(nextId) } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not load scenes.') }
  }

  const generate = async () => {
    if (!draftId) return
    setWorking(true); setStatus('Rendering deterministic 9:16 scenes…')
    try {
      const response = await fetch(`${apiBaseUrl}/api/images/scenes/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ draft_id: draftId }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not generate scenes.')
      setScenes(body.scenes); setStatus(`${body.scenes.length} scenes rendered at 1080 × 1920.`)
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not generate scenes.') } finally { setWorking(false) }
  }

  const validate = async () => {
    if (!draftId) return
    setWorking(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/images/scenes/${draftId}/validate`, { method: 'POST' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not validate scenes.')
      setScenes(body.scenes); setStatus(body.valid ? `All ${body.generated_scene_count} scenes passed validation.` : `${body.errors.length} validation issue(s) found.`)
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not validate scenes.') } finally { setWorking(false) }
  }

  const regenerate = async (scene: GeneratedScene) => {
    if (!draftId) return
    setWorking(true)
    try {
      const response = await fetch(`${apiBaseUrl}/api/images/scenes/${draftId}/${scene.scene_id}/regenerate`, { method: 'POST' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Could not regenerate scene.')
      await loadScenes(draftId); setStatus(`${scene.scene_type} scene regenerated. Validate when ready.`)
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not regenerate scene.') } finally { setWorking(false) }
  }

  return <>
    <header className="page-header"><p className="eyebrow">Scene workspace</p><h1>Accurate visuals for every Short.</h1><p>Text, options, answers, and diagrams are rendered deterministically from your accepted draft.</p></header>
    <section className="surface-card image-controls"><div><label className="field-label" htmlFor="draft-select">Accepted draft</label><select id="draft-select" value={draftId ?? ''} onChange={(event) => void selectDraft(event.target.value)} disabled={!drafts.length}>{drafts.length ? drafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.title}</option>) : <option>No accepted drafts yet</option>}</select></div><div className="image-actions"><button className="button" type="button" disabled={!draftId || working} onClick={() => void generate()}>{working ? 'Working…' : 'Generate Images'}</button><button className="button button-secondary" type="button" disabled={!draftId || !scenes.length || working} onClick={() => void validate()}>Validate scenes</button></div></section>
    {status && <div className="global-message" role="status">{status}</div>}
    {!drafts.length ? <section className="surface-card"><h2>No accepted drafts yet</h2><p className="muted">Generate an approved Short draft first, then return here to create its image sequence.</p></section> : <section className="scene-grid">{scenes.map((scene) => <article className="surface-card scene-card" key={scene.scene_id}><img src={`${apiBaseUrl}${scene.image_path}`} alt={`${scene.scene_type} scene`} /><div className="scene-card-body"><div><p className="eyebrow">Scene {scene.scene_number}</p><h2>{scene.scene_type}</h2></div><span className={`validation-pill ${scene.validation_status}`}>{scene.validation_status}</span></div><p className="muted">1080 × 1920 · {scene.generation_status}</p><button className="button button-secondary" type="button" disabled={working} onClick={() => void regenerate(scene)}>Regenerate</button></article>)}</section>}
  </>
}
