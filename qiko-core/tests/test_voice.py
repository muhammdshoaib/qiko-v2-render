from app.modules.ai.gateway import StubProvider
from app.modules.voice.pipeline import VoicePipeline, web_call_config
from app.modules.workers.config import WorkerConfig
from app.modules.workers.worker import build_worker

ISO = "IDG holds a current ISO 9001 certification valid through 2027."


class FakeSpeech:
    def transcribe(self, audio):
        return "Tell me about your ISO 9001 certification"

    def synthesize(self, text):
        return b"AUDIO:" + text.encode()


async def _worker():
    w = build_worker(WorkerConfig(name="idg", tenant="idg"), provider=StubProvider())
    await w.ingest("iso", ISO)
    return w


async def test_voice_pipeline_is_agentic_and_grounded():
    result = await VoicePipeline(FakeSpeech()).speak(await _worker(), "conv-1", b"<audio>")
    assert result.transcript.startswith("Tell me")     # STT output
    assert "ISO 9001" in result.answer                 # from agentcore, grounded in knowledge
    assert result.audio.startswith(b"AUDIO:")           # TTS produced audio from the answer


def test_web_call_config_has_no_secrets():
    cfg = web_call_config(model="amazon.nova-sonic-v1", region="eu-central-1")
    assert cfg["provider"] == "bedrock-nova-sonic"
    assert "key" not in str(cfg).lower()
