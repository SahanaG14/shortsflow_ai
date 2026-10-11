import { useState } from 'react'
import type { Channel, Preferences } from '../types'

type SettingsPageProps = { channel: Channel | null; preferences: Preferences; onReconnect: () => void; onSave: (preferences: Preferences) => Promise<void> }
const numberFormatter = new Intl.NumberFormat()
const defaultScheduleTimes = ['09:00', '18:00', '21:00']
const valueFor = (preferences: Preferences, key: string, fallback = '') => { const value = preferences[key]; return value === undefined || value === null ? fallback : Array.isArray(value) ? value.join(', ') : String(value) }
const dailyVideosFor = (preferences: Preferences) => { const configured = Number(preferences.videos_per_day); return Number.isInteger(configured) && configured > 0 ? configured : 1 }
const scheduleTimeFor = (index: number) => defaultScheduleTimes[index] ?? `${String((9 + index * 3) % 24).padStart(2, '0')}:00`
const readableTime = (value: string) => { const [hourText, minute] = value.split(':'); const hour = Number(hourText); return `${String(hour % 12 || 12).padStart(2, '0')}:${minute} ${hour >= 12 ? 'PM' : 'AM'}` }

function ToggleField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="toggle-row"><strong>{label}</strong><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /></label>
}

function SettingsForm({ channel, initialPreferences, onReconnect, onSave }: { channel: Channel | null; initialPreferences: Preferences; onReconnect: () => void; onSave: (preferences: Preferences) => Promise<void> }) {
  const [form, setForm] = useState<Preferences>(initialPreferences)
  const [uploadSchedule, setUploadSchedule] = useState(() => Array.from({ length: 24 }, (_, index) => scheduleTimeFor(index)))
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState('')
  const videosPerDay = dailyVideosFor(form)
  const update = (key: string, value: unknown) => setForm((current) => ({ ...current, [key]: value }))
  const updateNumber = (key: string, value: string) => update(key, value === '' ? undefined : Number(value))
  const save = async () => { setSaving(true); setFeedback(''); try { await onSave(form); setFeedback('Settings saved. Chat and new drafts now use these defaults.') } catch (error) { setFeedback(error instanceof Error ? error.message : 'Could not save settings.') } finally { setSaving(false) } }

  return <section className="page-stack">
    <header className="page-header"><p className="eyebrow">Workspace settings</p><h1>Set up your ShortsFlow workspace.</h1><p>These are permanent defaults. Chat can add temporary instructions for one draft without changing them.</p></header>
    {feedback && <div className="settings-feedback" role="status">{feedback}</div>}
    <div className="settings-grid">
      <section className="surface-card settings-card settings-channel"><div className="section-heading"><div><p className="eyebrow">Channel</p><h2>{channel?.title ?? 'No channel connected'}</h2><p className="muted">{channel ? 'Your YouTube connection is active.' : 'Connect a channel to sync its catalog and plan against existing videos.'}</p></div><span className={`connection-pill ${channel ? 'connected' : ''}`}>{channel ? 'Connected' : 'Not connected'}</span></div>{channel && <><div className="channel-detail-grid"><div><span>Channel ID</span><strong>{channel.channel_id}</strong></div><div><span>Subscribers</span><strong>{numberFormatter.format(channel.subscriber_count)}</strong></div><div><span>Channel videos</span><strong>{numberFormatter.format(channel.video_count)}</strong></div><div><span>Total views</span><strong>{numberFormatter.format(channel.view_count)}</strong></div></div>{channel.description && <p className="channel-description">{channel.description}</p>}</>}<div className="settings-actions"><button className="button" type="button" onClick={onReconnect}>{channel ? 'Reconnect channel' : 'Connect YouTube channel'}</button><button className="button button-secondary" type="button" disabled>Disconnect · coming soon</button></div></section>

      <section className="surface-card settings-card"><p className="eyebrow">Content preferences</p><h2>Creative defaults</h2><p className="muted">Saved to PostgreSQL and used as the starting point for every new draft.</p><div className="settings-form-grid"><label>Content categories<input value={valueFor(form, 'content_categories')} onChange={(event) => update('content_categories', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))} placeholder="CS, aptitude" /></label><label>Duration (seconds)<input type="number" min="1" value={valueFor(form, 'video_duration_seconds')} onChange={(event) => updateNumber('video_duration_seconds', event.target.value)} /></label><label>Language<input value={valueFor(form, 'language')} onChange={(event) => update('language', event.target.value)} placeholder="English" /></label><label>Theme<input value={valueFor(form, 'theme')} onChange={(event) => update('theme', event.target.value)} placeholder="dark navy" /></label><label>Options count<input type="number" min="0" value={valueFor(form, 'options_count')} onChange={(event) => updateNumber('options_count', event.target.value)} /></label><label>Thinking timer (seconds)<input type="number" min="1" value={valueFor(form, 'thinking_timer_seconds')} onChange={(event) => updateNumber('thinking_timer_seconds', event.target.value)} /></label><label>Videos per day<input type="number" min="1" value={valueFor(form, 'videos_per_day')} onChange={(event) => updateNumber('videos_per_day', event.target.value)} /></label></div><div className="settings-toggles settings-toggles-compact"><ToggleField label="Duplicate prevention" checked={form.duplicate_prevention_enabled === true} onChange={(value) => update('duplicate_prevention_enabled', value)} /></div><button className="button settings-save" type="button" onClick={() => void save()} disabled={saving}>{saving ? 'Saving settings…' : 'Save settings'}</button></section>

      <section className="surface-card settings-card"><p className="eyebrow">Generation settings</p><h2>What to include</h2><p className="muted">Generation uses the saved content defaults and the options below.</p><div className="settings-toggles"><ToggleField label="Generate title" checked onChange={() => undefined} /><ToggleField label="Generate description" checked onChange={() => undefined} /><ToggleField label="Generate hashtags" checked onChange={() => undefined} /><ToggleField label="Voiceover" checked={form.voiceover_enabled === true} onChange={(value) => update('voiceover_enabled', value)} /><label>Voice gender<select value={valueFor(form, 'voice_gender', 'male')} onChange={(event) => update('voice_gender', event.target.value)}><option value="male">Male</option><option value="female">Female</option></select></label><ToggleField label="Background music" checked={form.background_music_enabled === true} onChange={(value) => update('background_music_enabled', value)} /><ToggleField label="Answer explanation" checked={form.explanation_enabled === true} onChange={(value) => update('explanation_enabled', value)} /></div></section>

      <section className="surface-card settings-card"><p className="eyebrow">Upload settings</p><h2>Publishing defaults</h2><p className="muted">Generated videos will use these daily publishing slots when scheduling is available.</p><div className="upload-schedule"><div className="schedule-heading"><strong>Upload schedule</strong><span>{videosPerDay} video{videosPerDay === 1 ? '' : 's'} per day</span></div>{uploadSchedule.slice(0, videosPerDay).map((time, index) => <label className="schedule-slot" key={index}><span><strong>Video {index + 1}</strong><small>{readableTime(time)}</small></span><input aria-label={`Video ${index + 1} upload time`} type="time" value={time} onChange={(event) => setUploadSchedule((current) => current.map((currentTime, scheduleIndex) => scheduleIndex === index ? event.target.value : currentTime))} /></label>)}</div><div className="settings-toggles"><ToggleField label="Manual approval" checked onChange={() => undefined} /><ToggleField label="Auto-upload" checked={false} onChange={() => undefined} /></div></section>
    </div>
  </section>
}

export function SettingsPage({ channel, preferences, onReconnect, onSave }: SettingsPageProps) {
  return <SettingsForm key={JSON.stringify(preferences)} channel={channel} initialPreferences={preferences} onReconnect={onReconnect} onSave={onSave} />
}
