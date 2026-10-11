"""Voice provider abstraction for future Shorts renderers."""
from pathlib import Path
from typing import Protocol
import asyncio
import edge_tts

VOICE_IDS = {"male": "en-IN-PrabhatNeural", "female": "en-IN-NeerjaNeural"}
class VoiceProvider(Protocol):
    def synthesize(self, text: str, gender: str, destination: Path) -> dict[str, str]: ...
class EdgeTTSProvider:
    def synthesize(self, text: str, gender: str, destination: Path) -> dict[str, str]:
        voice = VOICE_IDS.get(gender, VOICE_IDS["male"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(edge_tts.Communicate(text, voice).save(str(destination)))
        return {"provider": "edge-tts", "voice": voice, "path": str(destination)}
