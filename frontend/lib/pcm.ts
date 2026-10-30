/**
 * PCM 工具：浏览器侧采样率转换与编解码。
 *
 * 关键约束（docs/技术实现步骤.md 步骤 1.2）：
 * - 必须读取**真实输入采样率**（44.1k / 48k 等），不能对所有设备硬套"三抽一"；
 * - 下采样前先低通，否则高频折叠成混叠噪声，识别率会莫名其妙下降；
 * - 服务端只接受 16kHz / 单声道 / PCM s16le。
 */

export const TARGET_SAMPLE_RATE = 16000;
export const FRAME_SAMPLES = 1600; // 100ms @16kHz
export const BYTES_PER_SAMPLE = 2;

/** 把任意采样率的 Float32 重采样到目标采样率（先低通，再线性插值）。 */
export function resampleToTarget(
  input: Float32Array,
  inputRate: number,
  targetRate: number = TARGET_SAMPLE_RATE
): Float32Array {
  if (inputRate === targetRate || input.length === 0) return input;

  // 下采样才需要抗混叠；上采样直接插值即可。
  let source = input;
  if (inputRate > targetRate) {
    const ratio = inputRate / targetRate;
    const window = Math.max(1, Math.round(ratio));
    source = new Float32Array(input.length);
    let sum = 0;
    for (let i = 0; i < input.length; i += 1) {
      sum += input[i];
      if (i >= window) sum -= input[i - window];
      source[i] = sum / Math.min(i + 1, window);
    }
  }

  const ratio = inputRate / targetRate;
  const outLength = Math.floor(source.length / ratio);
  const output = new Float32Array(outLength);
  for (let i = 0; i < outLength; i += 1) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, source.length - 1);
    const weight = position - left;
    output[i] = source[left] * (1 - weight) + source[right] * weight;
  }
  return output;
}

/** Float32 [-1,1] → PCM s16le 字节。 */
export function float32ToInt16Bytes(input: Float32Array): Uint8Array {
  const buffer = new ArrayBuffer(input.length * BYTES_PER_SAMPLE);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * BYTES_PER_SAMPLE, Math.round(clamped * 32767), true);
  }
  return new Uint8Array(buffer);
}

/** PCM s16le 字节 → Float32 [-1,1]。 */
export function int16BytesToFloat32(bytes: Uint8Array): Float32Array {
  const count = Math.floor(bytes.byteLength / BYTES_PER_SAMPLE);
  const output = new Float32Array(count);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let i = 0; i < count; i += 1) {
    output[i] = view.getInt16(i * BYTES_PER_SAMPLE, true) / 32768;
  }
  return output;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const step = 0x8000; // 分块避免超长参数导致栈溢出
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode(...bytes.subarray(i, i + step));
  }
  return btoa(binary);
}

export function base64ToBytes(data: string): Uint8Array {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** 帧拼接器：把不固定的回调块拼成固定的 100ms 网络帧。 */
export class FrameAssembler {
  private pending = new Float32Array(0);

  push(chunk: Float32Array): Float32Array[] {
    const merged = new Float32Array(this.pending.length + chunk.length);
    merged.set(this.pending, 0);
    merged.set(chunk, this.pending.length);

    const frames: Float32Array[] = [];
    let offset = 0;
    while (merged.length - offset >= FRAME_SAMPLES) {
      frames.push(merged.slice(offset, offset + FRAME_SAMPLES));
      offset += FRAME_SAMPLES;
    }
    this.pending = merged.slice(offset);
    return frames;
  }

  reset(): void {
    this.pending = new Float32Array(0);
  }
}
