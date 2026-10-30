"""两轮同连接S2S检测；不保存转写、回复正文或原始音频，不自动重试。"""
import asyncio
import base64
import json
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.voice.doubao import DuplexSession, DoubaoVoiceOptions, DoubaoVoiceError, diagnostics


async def probe(server_vad=False, output=None, question=None, audio=None, language=None):
    options = DoubaoVoiceOptions.from_settings(Settings(_env_file=ROOT / 'backend/.env'))
    session = DuplexSession(options, kind='realtime_probe')
    report = {'result': 'failed', 'rounds': [], 'persistent_connection': True, 'explicit_commit': not server_vad}
    with wave.open(str(audio or ROOT / 'docs/logs/2026-10-28/doubao-voice/sample.wav')) as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (16000, 1, 2)
        pcm = source.readframes(source.getnframes())
    try:
        if question:
            from app.voice.realtime import RealtimeDialogue
            dialogue = RealtimeDialogue(options)
            session = dialogue.session
            await dialogue.start({'content': question[:2000], 'language': language})
            report['question_context_characters'] = min(len(question), 2000)
        else:
            dialogue = None
            await session.start(instructions='你是中文口语陪练。用户询问身份时用一句不超过十五字的话回答。不要调用工具。')
        for index in range(2):
            row = {'round': index + 1, 'events': [], 'transcript_characters': 0, 'audio_bytes': 0, 'cancel_ack': False}
            report['rounds'].append(row)
            started = time.monotonic()
            async def receive():
                for _ in range(2000):
                    event = await session.receive()
                    kind = event['type']
                    row['events'].append(kind)
                    if dialogue:
                        translated = dialogue.translate(event)
                        if translated:
                            counts = row.setdefault('translated_events', {})
                            counts[translated['type']] = counts.get(translated['type'], 0) + 1
                    if kind.endswith('input_audio_transcription.completed'):
                        row['transcript_characters'] += len(event.get('transcript', event.get('text', '')))
                    if kind == 'response.output_audio.delta':
                        row['audio_bytes'] += len(base64.b64decode(event['delta'], validate=True))
                        row.setdefault('first_audio_ms', round((time.monotonic() - started) * 1000))
                        if index == 1 and not row.get('cancel_sent'):
                            row['cancel_sent'] = True
                            await session.send('response.cancel')
                    if kind == 'response.canceled':
                        row['cancel_ack'] = True
                        return
                    if kind == 'response.done' and row['audio_bytes'] and index == 0:
                        return
                raise DoubaoVoiceError('event_limit')
            reader = asyncio.create_task(receive())
            try:
                await session.send('input_audio_unmute.commit')
                audio = pcm + bytes(64000) if server_vad else pcm
                for offset in range(0, len(audio), 640):
                    await session.send('input_audio_buffer.append', audio=base64.b64encode(audio[offset:offset + 640]).decode())
                    await asyncio.sleep(.02)
                if not server_vad:
                    await session.send('input_audio_buffer.commit')
                await session.send('input_audio_mute.commit')
                await asyncio.wait_for(reader, 25)
            finally:
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
        report['result'] = 'passed' if all(r['audio_bytes'] and r['transcript_characters'] for r in report['rounds']) and report['rounds'][1]['cancel_ack'] else 'partial'
    except DoubaoVoiceError as exc:
        report['error_code'] = str(exc)
        report['http_status'] = exc.http_status
    except asyncio.TimeoutError:
        report['error_code'] = 'probe_timeout'
    finally:
        await session.close()
        report['transport'] = diagnostics()
        output = Path(output) if output else ROOT / ('docs/logs/2026-10-29/realtime-voice/probe-vad.json' if server_vad else 'docs/logs/2026-10-29/realtime-voice/probe.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real', action='store_true', required=True, help='明确允许联网检测两轮示例音频')
    parser.add_argument('--server-vad', action='store_true', help='只发送示例和静音，不发送强制结束事件')
    parser.add_argument('--json-out', type=Path, help='另存本批报告，保留历史证据')
    parser.add_argument('--question', help='使用生产陪练适配器和指定的合成题目上下文')
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--language', choices=['en'])
    args = parser.parse_args()
    asyncio.run(probe(args.server_vad, args.json_out, args.question, args.audio, args.language))
