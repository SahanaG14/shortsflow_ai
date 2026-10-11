"""Validated metadata, approval, scheduling and idempotent private uploads."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import select
from chat_preferences import get_preferences
from content_generation import list_generated_drafts
from database import GeneratedVideo, UploadRecord, session_scope
from video_rendering import VIDEO_DIRECTORY, validate_video
from youtube_oauth import upload_private_video

def _draft(draft_id): return next((item for item in list_generated_drafts() if item['id'] == draft_id), None)
def _metadata(draft, prefs):
    hashtags = [f"#{str(topic).replace(' ', '')}" for topic in draft.get('metadata', {}).get('category', '').split(',') if topic] or ['#Shorts']
    return {'title': draft['title'] if prefs.get('generate_title_enabled', True) else '', 'description': (draft.get('explanation') or '') if prefs.get('generate_description_enabled', True) else '', 'hashtags': hashtags if prefs.get('generate_hashtags_enabled', True) else []}
def _slot(prefs, occupied):
    timezone = ZoneInfo(str(prefs.get('timezone', 'Asia/Kolkata')))
    count = max(1, int(prefs.get('videos_per_day', 1)))
    times = list(prefs.get('upload_schedule_times', ['09:00','18:00','21:00']))[:count]
    now = datetime.now(timezone)
    for day in range(0, 31):
        date = (now + timedelta(days=day)).date()
        for value in times:
            hour, minute = map(int, str(value).split(':'))
            candidate = datetime(date.year,date.month,date.day,hour,minute,tzinfo=timezone)
            if candidate > now and candidate.astimezone(UTC) not in occupied: return candidate.astimezone(UTC)
    raise ValueError('No upload slot is available in the next 31 days.')
def _dict(r): return {'id':r.id,'video_render_id':r.video_render_id,'draft_id':r.draft_id,'youtube_video_id':r.youtube_video_id,'title':r.title,'description':r.description,'hashtags':r.hashtags,'privacy_status':r.privacy_status,'scheduled_at':r.scheduled_at.isoformat() if r.scheduled_at else None,'upload_state':r.upload_state,'attempt_count':r.attempt_count,'last_error':r.last_error}
def prepare_upload(draft_id):
    validation = validate_video(draft_id)
    if not validation['valid']: raise ValueError('Only successfully validated videos can enter upload workflow.')
    with session_scope() as s:
        video=s.scalar(select(GeneratedVideo).where(GeneratedVideo.draft_id==draft_id)); existing=s.scalar(select(UploadRecord).where(UploadRecord.video_render_id==video.id))
        if existing:return _dict(existing)
        prefs=get_preferences(); draft=_draft(draft_id); data=_metadata(draft,prefs)
        occupied=set(s.scalars(select(UploadRecord.scheduled_at).where(UploadRecord.scheduled_at.is_not(None))).all())
        record=UploadRecord(video_render_id=video.id,draft_id=draft_id,privacy_status='private',upload_state='ready' if prefs.get('manual_approval_enabled', True) else 'scheduled',scheduled_at=_slot(prefs,occupied),**data); s.add(record); s.flush(); return _dict(record)
def list_uploads():
    with session_scope() as s:return [_dict(x) for x in s.scalars(select(UploadRecord).order_by(UploadRecord.id.desc())).all()]
def upload(record_id, client_secret, token_file):
    with session_scope() as s:
        record=s.get(UploadRecord,record_id)
        if not record: raise ValueError('Upload record was not found.')
        if record.youtube_video_id: return _dict(record)
        if not record.title: raise ValueError('A title is required before upload.')
        video=s.get(GeneratedVideo,record.video_render_id); path=VIDEO_DIRECTORY / video.video_path.removeprefix('/generated-videos/')
        record.attempt_count += 1
        try:
            record.youtube_video_id=upload_private_video(client_secret,token_file,path,record.title,record.description,record.hashtags); record.upload_state='published'; record.last_error=''
        except Exception as error:
            record.upload_state='failed'; record.last_error=str(error); raise
        finally: s.flush()
        return _dict(record)
