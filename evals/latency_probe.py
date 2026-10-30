"""语音链路分段延迟探针（P1 步骤 1.6）。

设计约束（评审要求，docs/技术实现步骤.md 步骤 1.4/1.6）：

1. **分段打点，不只看端到端**：把一轮语音问答拆成
   `用户停口 → ASR final → 首业务事件 → TTS 首片 → TTS 结束`，
   延迟超标时能直接定位环节。
2. **"用户停口→播放"与"VAD确认→播放"必须分列**：前者含 700ms 静默等待，
   不能通过切换起点把它掩盖掉。
3. **跨机时钟不可相减**：服务端段（VAD 判定 → 首片下发）用**服务端单调时钟**
   的两个戳相减（`t_vad_end` / `t_emit`，同源可减）；
   浏览器实际播放耗时必须由前端打点，经 `--client-timings` 传入，
   未提供时明确报"未测量"，不得用服务端数字冒充。
4. **一轮一场面试**：面试是有限状态机（主题问完即收尾），
   复用同一场会导致后续轮次没有 current_question。
5. **帧按真实节拍发送**：100ms/帧。若一次性灌完，"用户停口"时刻就无从定义，
   含静默等待的口径会算出负值（这正是首版探针的缺陷）。

DummyASR/DummyTTS 只反映**管道开销**，不含真实识别与合成耗时，
因此本脚本的数字**不能**当作真实链路指标；接入真实供应商后需重跑。

用法：
    # 服务端需以语音模式启动，例如：
    #   VOICE_ENABLED=true VOICE_ASR_DUMMY_TEXT="这是一段测试回答"
    #   DATABASE_URL="sqlite:///D:/probe.db" uvicorn app.main:app --port 8211
    python evals/latency_probe.py --base-url http://127.0.0.1:8211 --turns 12
    python evals/latency_probe.py --turns 12 --concurrency 2 --json-out out.json
    python evals/latency_probe.py --client-timings client.json
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import statistics
import sys
import time
import urllib.request

try:
    import websockets
except ImportError:  # pragma: no cover
    print("缺少依赖：pip install websockets", file=sys.stderr)
    raise

LOUD = (9000).to_bytes(2, "little", signed=True) * 1600
SILENT = b"\x00\x00" * 1600
FRAME_MS = 100.0
#: 与后端默认 voice_silence_ms 一致：这是"用户停口→VAD 判定"的固定等待，
#: 必须计入"用户停口→播放"口径，不能从 VAD 判定点起算来美化数字。
SILENCE_MS = 700.0
VOICE_FRAMES = [LOUD] * 2 + [SILENT] * 7


def _no_proxy_opener() -> None:
    urllib.request.install_opener(
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
    )


def b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode()


def http_json(url: str, payload: dict | None = None) -> dict:
    if payload is None:
        request = urllib.request.Request(url)
    else:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


class Recorder:
    """单轮计时。客户端各段用**本机单调时钟**；服务端段用服务端戳差。"""

    def __init__(self) -> None:
        self.marks: dict[str, float] = {}
        self.server: dict[str, float] = {}
        self.failed = False
        self.fail_reason = ""

    def mark(self, name: str) -> None:
        self.marks.setdefault(name, time.monotonic())

    def segment(self, start: str, end: str) -> float | None:
        if start in self.marks and end in self.marks:
            return (self.marks[end] - self.marks[start]) * 1000.0
        return None

    def server_segment(self, start: str, end: str) -> float | None:
        if start in self.server and end in self.server:
            return (self.server[end] - self.server[start]) * 1000.0
        return None


async def run_turn(base: str, created: dict) -> Recorder:
    rec = Recorder()
    url = base.replace("https://", "wss://").replace("http://", "ws://")

    async with websockets.connect(
        f"{url}/ws/interview/{created['interview_id']}",
        subprotocols=["interview", created["access_token"]],
    ) as ws:
        await ws.send(json.dumps({"type": "start"}))
        snapshot = json.loads(await ws.recv())
        if snapshot.get("type") != "snapshot":
            rec.failed, rec.fail_reason = True, f"start 未返回 snapshot: {snapshot.get('type')}"
            return rec
        question = snapshot.get("current_question")
        if not question:
            rec.failed, rec.fail_reason = True, "面试已结束，没有待答问题"
            return rec
        turn_id = question["turn_id"]

        # 按 100ms 真实节拍发送：这样"用户停口"才有明确定义。
        # 若一次性灌完，含静默等待的口径会算出负延迟（首版探针的缺陷）。
        for seq, pcm in enumerate(VOICE_FRAMES):
            await ws.send(json.dumps({
                "type": "audio", "turn_id": turn_id, "seq": seq,
                "format": "pcm_s16le", "sample_rate": 16000, "channels": 1,
                "data": b64(pcm),
            }))
            if seq == 1:
                # 最后一帧语音（index 1）发送完成 = 用户停口时刻。
                # 之后的静默帧不计入用户说话时间。
                rec.mark("speech_stop")
            if seq + 1 < len(VOICE_FRAMES):
                await asyncio.sleep(FRAME_MS / 1000.0)
        if "speech_stop" not in rec.marks:
            rec.failed, rec.fail_reason = True, "音频帧未按预期发送"
            return rec

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                event = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                rec.failed, rec.fail_reason = True, "等待事件超时/连接关闭"
                break
            kind = event.get("type")
            if kind == "error":
                rec.failed, rec.fail_reason = True, event.get("detail", "server error")
                break
            if kind == "asr_final":
                rec.mark("asr_final_recv")
                if event.get("t_vad_end") is not None:
                    rec.server["t_vad_end"] = float(event["t_vad_end"])
            elif kind in ("answer_ack", "score"):
                rec.mark("first_turn_event")
            elif kind in ("question", "agent_message", "closing", "report_ready"):
                rec.mark("first_speakable")
            elif kind == "tts_chunk":
                rec.mark("first_tts_recv")
                if event.get("t_emit") is not None:
                    rec.server["t_emit"] = float(event["t_emit"])
            elif kind == "tts_end":
                rec.mark("tts_end_recv")
                break
        return rec


async def measure(base: str, turns: int, concurrency: int) -> list[Recorder]:
    _no_proxy_opener()
    health = http_json(f"{base}/api/health")
    if health.get("status") != "ok":
        raise SystemExit(f"服务端不可用：{health}")

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def worker() -> Recorder:
        async with semaphore:
            try:
                # 每轮一场新面试：面试是有限过程，复用会导致后续无题可答。
                created = http_json(
                    f"{base}/api/interview",
                    {"position": "java_backend", "difficulty": "mid"},
                )
                return await run_turn(base, created)
            except Exception as exc:  # 单轮异常不影响整体统计
                rec = Recorder()
                rec.failed, rec.fail_reason = True, f"{type(exc).__name__}: {exc}"
                return rec

    return list(await asyncio.gather(*(worker() for _ in range(turns))))


def summarize(records: list[Recorder], label: str, silence_ms: float) -> dict:
    ok = [r for r in records if not r.failed]

    def collect(extractor) -> list[float]:
        return [v for v in (extractor(r) for r in ok) if v is not None]

    # 客户端单调时钟（含 700ms 静默等待，口径不可美化为 VAD 判定起算）
    client_segments = {
        "speech_stop_to_asr_final": collect(lambda r: r.segment("speech_stop", "asr_final_recv")),
        "speech_stop_to_first_tts": collect(lambda r: r.segment("speech_stop", "first_tts_recv")),
        "asr_final_to_first_tts": collect(lambda r: r.segment("asr_final_recv", "first_tts_recv")),
        "first_tts_to_tts_end": collect(lambda r: r.segment("first_tts_recv", "tts_end_recv")),
    }
    # 服务端单调时钟（同源相减合法；不含浏览器播放）
    server_segments = {
        "vad_to_first_tts_emit": collect(lambda r: r.server_segment("t_vad_end", "t_emit")),
    }

    def stats(values: list[float]) -> dict:
        return {
            "n": len(values),
            "p50": round(pct(values, 0.50), 1),
            "p95": round(pct(values, 0.95), 1),
            "mean": round(statistics.fmean(values), 1),
            "max": round(max(values), 1),
        }

    report: dict = {
        "label": label,
        "samples": len(records),
        "ok": len(ok),
        "failed": len(records) - len(ok),
        "failure_rate": round((len(records) - len(ok)) / max(len(records), 1), 4),
        "clock_note": (
            "client_* 为客户端单调时钟分段；server_* 为服务端单调时钟分段。"
            "跨机时钟不可相减，故分列。"
        ),
        "silence_wait_ms": silence_ms,
        "note": "DummyASR/DummyTTS 只反映管道开销，不含真实识别与合成耗时",
        "client_segments_ms": {k: stats(v) for k, v in client_segments.items() if v},
        "server_segments_ms": {k: stats(v) for k, v in server_segments.items() if v},
    }
    if ok and not any(r.marks.get("first_tts_recv") for r in ok):
        report["warning"] = "没有任何 tts_chunk：请确认 VOICE_ENABLED=true 且 TTS 通路可用"
    if any(r.failed for r in records):
        report["fail_reasons"] = sorted(
            {r.fail_reason for r in records if r.failed and r.fail_reason}
        )[:5]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="语音链路分段延迟探针")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--turns", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=2, help="冷启动预热轮数（不计入统计）")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--silence-ms", type=float, default=SILENCE_MS,
                        help="后端 voice_silence_ms，用于标注口径")
    parser.add_argument("--client-timings", help="前端打点 JSON（浏览器实际播放耗时）")
    parser.add_argument("--json-out", help="把结果写入文件")
    args = parser.parse_args()

    if args.warmup:
        print(f"预热 {args.warmup} 轮（冷启动，不计入统计）…")
        asyncio.run(measure(args.base_url, args.warmup, 1))

    print(f"测量 {args.turns} 轮，并发 {args.concurrency} …")
    records = asyncio.run(measure(args.base_url, args.turns, args.concurrency))
    report = summarize(records, f"concurrency={args.concurrency}", args.silence_ms)

    if args.client_timings:
        try:
            with open(args.client_timings, encoding="utf-8") as handle:
                client = json.load(handle)
            play = [float(v) for v in client.get("tts_first_chunk_to_play_ms", [])]
            if play:
                report["browser_playback_ms"] = {
                    "n": len(play),
                    "p50": round(pct(play, 0.50), 1),
                    "p95": round(pct(play, 0.95), 1),
                    "source": "浏览器打点（与本机时钟不可直接相减，故单独列出）",
                }
        except (OSError, ValueError, KeyError) as exc:
            report["client_timings_error"] = f"{type(exc).__name__}: {exc}"
    else:
        report["browser_playback_ms"] = "未测量（需前端打点后经 --client-timings 传入）"

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"已写入 {args.json_out}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
