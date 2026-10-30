/**
 * 语音 AudioWorklet：采集与播放两个处理器。
 *
 * 为什么用 AudioWorklet 而不是 ScriptProcessorNode：
 * 后者已废弃，且在音频线程之外运行，长播放会累积漂移。
 *
 * 采样的重采样不在这里做——Worklet 只负责把原生采样率的数据块送出，
 * 重采样与低通在主线程完成（见 lib/pcm.ts），便于单测与复用。
 */

class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    // 必须拷贝：input 的底层缓冲会被复用，直接 post 会拿到被覆盖的数据。
    this.port.postMessage(input[0].slice());
    return true;
  }
}
registerProcessor("capture-processor", CaptureProcessor);

/** 有界播放缓冲：队列满时丢弃**最旧**数据，保证延迟不会无限增长。 */
class PlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.offset = 0;
    this.maxSamples = 0;
    this.port.onmessage = (event) => {
      const data = event.data || {};
      if (data.type === "config") {
        this.maxSamples = data.maxSamples || 0;
      } else if (data.type === "push" && data.samples) {
        this.queue.push(data.samples);
        this.trim();
      } else if (data.type === "clear") {
        this.queue = [];
        this.offset = 0;
      }
    };
  }

  trim() {
    if (!this.maxSamples) return;
    let total = -this.offset;
    for (const item of this.queue) total += item.length;
    while (total > this.maxSamples && this.queue.length > 1) {
      total -= this.queue.shift().length;
    }
  }

  process(_inputs, outputs) {
    const out = outputs[0] && outputs[0][0];
    if (!out) return true;
    let written = 0;
    while (written < out.length) {
      if (this.queue.length === 0) {
        out[written] = 0;
        written += 1;
        continue;
      }
      const current = this.queue[0];
      const take = Math.min(out.length - written, current.length - this.offset);
      out.set(current.subarray(this.offset, this.offset + take), written);
      this.offset += take;
      written += take;
      if (this.offset >= current.length) {
        this.queue.shift();
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("playback-processor", PlaybackProcessor);
