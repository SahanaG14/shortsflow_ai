import type { Channel, DuplicateResult, Video } from '../types'

type HomePageProps = {
  channel: Channel | null
  loading: boolean
  videos: Video[]
  draftCount: number
  syncing: boolean
  duplicateResult: DuplicateResult | null
  proposedTitle: string
  onProposedTitleChange: (value: string) => void
  onConnect: () => void
  onSync: () => void
  onCheckDuplicate: () => void
  checkingDuplicate: boolean
}

const formatter = new Intl.NumberFormat()

export function HomePage({ channel, loading, videos, draftCount, syncing, duplicateResult, proposedTitle, onProposedTitleChange, onConnect, onSync, onCheckDuplicate, checkingDuplicate }: HomePageProps) {
  return (
    <section className="page-stack">
      <header className="page-header home-header">
        <div><p className="eyebrow">Dashboard overview</p><h1>Keep your Shorts pipeline moving.</h1><p>Monitor your Shorts performance and keep the local video catalog ready for the next idea.</p></div>
      </header>
      {loading && <div className="surface-card muted">Loading your connected channel…</div>}
      {!loading && !channel && <div className="surface-card empty-state"><h2>Connect your YouTube channel</h2><p>Bring in your current performance and video catalog to start planning smarter Shorts.</p><button className="button" type="button" onClick={onConnect}>Connect YouTube channel</button></div>}
      {channel && <>
        <div className="surface-card dashboard-action"><div><p className="eyebrow">Catalog status</p><h2>Your Shorts workspace is ready.</h2><p>Keep the local catalog current before planning your next idea.</p></div><button className="button" type="button" onClick={onSync} disabled={syncing}>{syncing ? 'Syncing videos…' : 'Sync videos'}</button></div>
        <div className="metric-grid">
          <Metric label="Subscribers" value={formatter.format(channel.subscriber_count)} />
          <Metric label="Channel videos" value={formatter.format(channel.video_count)} />
          <Metric label="Total views" value={formatter.format(channel.view_count)} />
          <Metric label="Synced videos" value={formatter.format(videos.length)} />
          <Metric label="Generated drafts" value={formatter.format(draftCount)} />
        </div>
        <div className="dashboard-grid">
          <section className="surface-card"><div className="section-heading"><div><p className="eyebrow">Catalog health</p><h2>Recent synced videos</h2></div><span className="count-pill">{videos.length} local</span></div><div className="compact-video-list">{videos.slice(0, 4).map((video) => <article className="compact-video" key={video.youtube_video_id}>{video.thumbnail_url && <img src={video.thumbnail_url} alt="" />}<div><h3>{video.title}</h3><p>{new Date(video.published_at).toLocaleDateString()}</p></div></article>)}</div></section>
          <section className="surface-card"><p className="eyebrow">Quick workflow</p><h2>Plan with confidence</h2><p className="muted">Sync the catalog, shape preferences in Chat, then generate a duplicate-safe Short draft.</p><div className="workflow-steps"><span>1. Sync</span><span>2. Plan</span><span>3. Generate</span></div><label className="field-label" htmlFor="proposed-title">Quick duplicate check</label><input id="proposed-title" value={proposedTitle} onChange={(event) => onProposedTitleChange(event.target.value)} placeholder="e.g. BFS vs DFS explained" /><button className="button" type="button" onClick={onCheckDuplicate} disabled={checkingDuplicate}>{checkingDuplicate ? 'Checking…' : 'Check duplicate'}</button>{duplicateResult && <div className={`result-banner ${duplicateResult.is_duplicate ? 'warning' : 'success'}`}><strong>{duplicateResult.is_duplicate ? 'Potential overlap found' : 'Safe to create'}</strong><p>{duplicateResult.reason}</p>{duplicateResult.matched_title && <p>Matched: {duplicateResult.matched_title}</p>}</div>}</section>
        </div>
      </>}
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return <article className="metric-card"><p>{label}</p><strong>{value}</strong></article>
}
