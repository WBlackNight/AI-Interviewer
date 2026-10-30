"""有限豆包语音联调：默认只查配置；--real才上传示例短音频和合成一句话。"""
import argparse
import asyncio
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import wave
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import Settings
from app.voice.doubao import DoubaoASR, DoubaoTTS, DoubaoVoiceOptions, DoubaoVoiceError, diagnostics


async def probe(settings, sample_zip, audio_out):
    options = DoubaoVoiceOptions.from_settings(settings)
    report = {'result': 'failed', 'protocol': 'seeduplex-json', 'auth_mode': options.auth_mode, 'external_sessions_attempted': 0,
              'quality_verified': False, 'billing_verified': False}
    # 仅读取压缩包内指定WAV，不解压或执行任何示例代码。
    with ZipFile(sample_zip) as bundle:
        member = bundle.getinfo('python3.7_duplex_demo/whoareyou.wav')
        if member.file_size > 32000 * 10 + 65536:
            raise ValueError('sample_size')
        raw = bundle.read(member)
    with wave.open(io.BytesIO(raw), 'rb') as source:
        if (source.getnchannels(), source.getframerate(), source.getsampwidth(), source.getcomptype()) != (1, 16000, 2, 'NONE'):
            raise ValueError('sample_format')
        pcm = source.readframes(source.getnframes())
    report['input'] = {'seconds': len(pcm) / 32000, 'sha256': hashlib.sha256(raw).hexdigest()}
    asr, tts = DoubaoASR(options), DoubaoTTS(options)
    stage = 'asr'
    try:
        report['external_sessions_attempted'] += 1
        started = time.perf_counter()
        await asr.start()
        for offset in range(0, len(pcm), 3200):
            events = await asr.feed(pcm[offset:offset + 3200], sample_rate=16000)
            if any(event.is_final for event in events):
                break
            await asyncio.sleep(.1)
        text = await asr.finish()
        report['asr'] = {'completed': bool(text), 'characters': len(text),
                         'elapsed_ms': round((time.perf_counter() - started) * 1000)}
        stage = 'tts'
        report['external_sessions_attempted'] += 1
        started = time.perf_counter()
        output = bytearray()
        first = None
        async for chunk in tts.synthesize('你好，请介绍你的技术项目。'):
            if first is None:
                first = round((time.perf_counter() - started) * 1000)
            output.extend(chunk)
        report['tts'] = {'completed': bool(output), 'bytes': len(output), 'sample_rate': 24000,
                         'first_chunk_ms': first, 'seconds': len(output) / 48000,
                         'non_silent': any(output)}
        if not text or not output or not any(output):
            raise DoubaoVoiceError('empty_audio_or_transcript')
        if audio_out:
            audio_out.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(audio_out), 'wb') as target:
                target.setnchannels(1); target.setsampwidth(2); target.setframerate(24000)
                target.writeframes(output)
        report['result'] = 'passed'
    except Exception as exc:
        report.update(failed_stage=stage, error_code=str(exc) if isinstance(exc, DoubaoVoiceError) else 'probe_error')
        if isinstance(exc, DoubaoVoiceError):
            report.update(http_status=exc.http_status, request_id=exc.request_id)
    finally:
        await asr.close(); await tts.close()
    report['transport'] = diagnostics()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--sample-zip', type=Path)
    parser.add_argument('--json-out', type=Path)
    parser.add_argument('--audio-out', type=Path)
    args = parser.parse_args()
    for path in (args.json_out, args.audio_out):
        if path and (not path.resolve().is_relative_to(ROOT / 'docs/logs') or path.resolve() == args.sample_zip):
            parser.error('output_must_be_under_docs_logs')
    settings = Settings(_env_file=ROOT / 'backend/.env', voice_enabled=False,
                        doubao_voice_timeout_seconds=15, doubao_voice_session_seconds=30)
    configured = bool(settings.doubao_voice_app_id and settings.doubao_voice_access_token) if settings.doubao_voice_auth_mode == 'legacy' else bool(settings.doubao_voice_api_key)
    report = {'result': 'not_run', 'configured': configured, 'auth_mode': settings.doubao_voice_auth_mode,
              'external_sessions_attempted': 0, 'quality_verified': False}
    if args.real and not configured:
        report['result'] = 'credentials_missing'
    elif args.real:
        if not args.sample_zip:
            parser.error('--real_requires_sample_zip')
        try:
            report = asyncio.run(probe(settings, args.sample_zip, args.audio_out))
        except Exception:
            report = {'result': 'failed', 'error_code': 'invalid_sample', 'external_sessions_attempted': 0}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['result'] in ('passed', 'not_run') else 1


if __name__ == '__main__':
    sys.exit(main())
