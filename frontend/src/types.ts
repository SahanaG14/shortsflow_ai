export type Channel = {
  channel_id: string
  title: string
  description: string
  subscriber_count: number
  video_count: number
  view_count: number
}

export type Video = {
  youtube_video_id: string
  title: string
  description: string
  published_at: string
  thumbnail_url: string
}

export type SyncResult = {
  fetched_count: number
  inserted_count: number
  updated_count: number
  total_stored_count: number
}

export type DuplicateResult = {
  is_duplicate: boolean
  duplicate_type: 'exact_title' | 'similar_title' | 'similar_topic' | 'none'
  similarity_score: number
  matched_video_id: string | null
  matched_title: string | null
  reason: string
}

export type ChatMessage = { role: 'user' | 'assistant'; content: string; created_at: string }
export type AssistantMessage = { role: 'user' | 'assistant'; content: string; tools_used?: string[]; created_at?: string }
export type Preferences = Record<string, unknown>

export type DuplicateCheckHistory = {
  attempt: number
  candidate_title: string
  accepted: boolean
  duplicate_type: string
  similarity_score: number
  matched_title: string | null
  reason: string
}

export type GeneratedDraft = {
  id: number
  topic: string
  title: string
  hook: string
  question: string
  options: string[]
  correct_answer: string
  explanation: string | null
  scene_script: string
  target_duration_seconds: number
}

export type GeneratedScene = {
  id: number
  scene_id: string
  draft_id: number
  scene_number: number
  scene_type: string
  image_path: string
  generation_status: string
  validation_status: string
  render_data: Record<string, unknown>
}

export type RenderedVideo = {
  id: number
  draft_id: number
  render_status: string
  video_path: string
  duration_seconds: number | null
  width: number | null
  height: number | null
  file_size_bytes: number | null
  validation_status: string
  timeline: Array<{ scene_id: string; scene_number: number; scene_type: string; duration_seconds: number; countdown_value?: number; narration_text?: string; speech_duration_seconds?: number; visual_start_seconds?: number; visual_end_seconds?: number }>
  audio_expected: boolean
  audio_note: string
  voiceover_enabled: boolean
  voice_provider: string
  voice_gender: string
  voice_id: string
  audio_path: string
  audio_duration_seconds: number | null
  countdown_length: number
}

export type AppRoute = '/' | '/home' | '/chat' | '/images' | '/video' | '/uploads' | '/profile'
