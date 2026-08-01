import type {
  HcaDecodeRequest,
  HcaDecodeResponse,
} from './hca/hca-worker.ts';
import {
  getExedraVoiceUrl,
  getMagirecoVoiceProxyUrl,
  parseVoiceCue,
} from './voice-cue.ts';
import {
  getMagirecoVoiceUpstreamUrl,
  MAX_VOICE_BYTES,
} from './voice-proxy.ts';

export type VoicePlaybackStatus = 'idle' | 'loading' | 'playing' | 'error';

export interface VoicePlaybackState {
  cueId: string | null;
  error: string | null;
  status: VoicePlaybackStatus;
}

type StateListener = () => void;

const IDLE_STATE: VoicePlaybackState = {
  cueId: null,
  error: null,
  status: 'idle',
};
const NETWORK_TIMEOUT_MS = 30_000;
const PLAYBACK_CEILING_MS = 90_000;
const RETRYABLE_PROXY_STATUSES = new Set([502, 503, 504]);

type VoiceFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

/**
 * Keep the same-origin Worker proxy as the primary source. If the proxy cannot
 * reach the voice bucket, use the bucket's fixed public URL as a bounded
 * browser-side fallback. The bucket CORS policy only permits the known reader
 * and viewer origins.
 */
export async function fetchMagirecoVoiceResponse(
  cueId: string,
  signal: AbortSignal,
  fetchVoice: VoiceFetch = fetch,
): Promise<Response> {
  let proxyResponse: Response | null = null;
  try {
    proxyResponse = await fetchVoice(getMagirecoVoiceProxyUrl(cueId), {
      cache: 'no-store',
      credentials: 'same-origin',
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
  }

  if (proxyResponse?.ok) return proxyResponse;
  if (
    proxyResponse &&
    !RETRYABLE_PROXY_STATUSES.has(proxyResponse.status)
  ) {
    throw new Error(`魔法纪录语音加载失败 (${proxyResponse.status})`);
  }

  const directResponse = await fetchVoice(
    getMagirecoVoiceUpstreamUrl(cueId),
    {
      cache: 'no-store',
      credentials: 'omit',
      mode: 'cors',
      signal,
    },
  );
  if (!directResponse.ok) {
    throw new Error(`魔法纪录语音加载失败 (${directResponse.status})`);
  }
  return directResponse;
}

async function readBodyBounded(
  response: Response,
  signal: AbortSignal,
): Promise<ArrayBuffer> {
  const declaredLength = Number(response.headers.get('content-length') ?? '0');
  if (
    Number.isFinite(declaredLength) &&
    declaredLength > MAX_VOICE_BYTES
  ) {
    throw new Error('语音文件超过 8 MiB 安全上限');
  }
  if (!response.body) throw new Error('语音响应没有正文');

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_VOICE_BYTES) {
        await reader.cancel('Voice object exceeds size limit');
        throw new Error('语音文件超过 8 MiB 安全上限');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return merged.buffer;
}

class VoicePlaybackController {
  private state: VoicePlaybackState = IDLE_STATE;
  private readonly listeners = new Set<StateListener>();
  private generation = 0;
  private fetchAbort: AbortController | null = null;
  private worker: Worker | null = null;
  private workerReject: ((reason: Error) => void) | null = null;
  private nativeAudio: HTMLAudioElement | null = null;
  private audioContext: AudioContext | null = null;
  private audioSource: AudioBufferSourceNode | null = null;
  private operationTimer: ReturnType<typeof setTimeout> | null = null;

  getSnapshot = (): VoicePlaybackState => this.state;

  getServerSnapshot = (): VoicePlaybackState => IDLE_STATE;

  subscribe = (listener: StateListener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private update(next: VoicePlaybackState): void {
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  private clearTimer(): void {
    if (this.operationTimer !== null) {
      clearTimeout(this.operationTimer);
      this.operationTimer = null;
    }
  }

  private releaseResources(): void {
    this.clearTimer();
    this.fetchAbort?.abort();
    this.fetchAbort = null;
    const workerReject = this.workerReject;
    this.workerReject = null;
    this.worker?.terminate();
    this.worker = null;
    workerReject?.(new DOMException('Aborted', 'AbortError'));

    if (this.nativeAudio) {
      this.nativeAudio.onerror = null;
      this.nativeAudio.onended = null;
      this.nativeAudio.pause();
      this.nativeAudio.removeAttribute('src');
      this.nativeAudio.load();
      this.nativeAudio = null;
    }
    if (this.audioSource) {
      this.audioSource.onended = null;
      try {
        this.audioSource.stop();
      } catch {
        // Already stopped.
      }
      this.audioSource.disconnect();
      this.audioSource = null;
    }
    if (this.audioContext) {
      void this.audioContext.close();
      this.audioContext = null;
    }
  }

  stop = (): void => {
    this.generation += 1;
    this.releaseResources();
    this.update(IDLE_STATE);
  };

  toggle = async (cueId: string): Promise<void> => {
    if (
      this.state.cueId === cueId &&
      (this.state.status === 'loading' || this.state.status === 'playing')
    ) {
      this.stop();
      return;
    }
    await this.play(cueId);
  };

  play = async (cueId: string): Promise<void> => {
    const cue = parseVoiceCue(cueId);
    if (!cue) {
      this.stop();
      this.update({
        cueId,
        error: '无效的语音编号',
        status: 'error',
      });
      return;
    }
    if (typeof window === 'undefined') return;

    this.generation += 1;
    const currentGeneration = this.generation;
    this.releaseResources();
    this.update({ cueId, error: null, status: 'loading' });
    this.operationTimer = setTimeout(() => {
      if (this.generation === currentGeneration) this.stop();
    }, PLAYBACK_CEILING_MS);

    try {
      if (cue.system === 'exedra') {
        await this.playExedra(cue.id, currentGeneration);
      } else {
        await this.playMagireco(cue.id, currentGeneration);
      }
    } catch (error) {
      if (this.generation !== currentGeneration) return;
      this.releaseResources();
      this.update({
        cueId,
        error:
          error instanceof Error
            ? error.message
            : '语音播放失败',
        status: 'error',
      });
    }
  };

  private async playExedra(
    cueId: string,
    currentGeneration: number,
  ): Promise<void> {
    const audio = new Audio();
    this.nativeAudio = audio;
    audio.preload = 'none';
    audio.src = getExedraVoiceUrl(cueId);
    audio.onended = () => {
      if (this.generation === currentGeneration) this.stop();
    };
    audio.onerror = () => {
      if (this.generation !== currentGeneration) return;
      this.releaseResources();
      this.update({
        cueId,
        error: 'Exedra Wiki 语音无法加载',
        status: 'error',
      });
    };
    await audio.play();
    if (this.generation !== currentGeneration) {
      audio.pause();
      return;
    }
    this.update({ cueId, error: null, status: 'playing' });
  }

  private async playMagireco(
    cueId: string,
    currentGeneration: number,
  ): Promise<void> {
    // Create the single context while the click still counts as a user
    // activation. Some browsers keep a context created after an awaited fetch
    // suspended indefinitely.
    const audioContext = new AudioContext();
    this.audioContext = audioContext;
    void audioContext.resume();

    const abortController = new AbortController();
    this.fetchAbort = abortController;
    const networkTimer = setTimeout(
      () => abortController.abort(),
      NETWORK_TIMEOUT_MS,
    );
    let bytes: ArrayBuffer;
    try {
      const response = await fetchMagirecoVoiceResponse(
        cueId,
        abortController.signal,
      );
      bytes = await readBodyBounded(response, abortController.signal);
    } finally {
      clearTimeout(networkTimer);
      if (this.fetchAbort === abortController) this.fetchAbort = null;
    }
    if (this.generation !== currentGeneration) return;

    const decoded = await this.decodeHca(bytes, currentGeneration);
    if (this.generation !== currentGeneration) return;

    await audioContext.resume();
    const frameCount = decoded.channels[0]?.length ?? 0;
    if (frameCount === 0 || decoded.channels.some(c => c.length !== frameCount)) {
      throw new Error('解码后的语音声道无效');
    }
    const audioBuffer = audioContext.createBuffer(
      decoded.channels.length,
      frameCount,
      decoded.sampleRate,
    );
    decoded.channels.forEach((channel, index) => {
      audioBuffer.copyToChannel(channel, index);
    });

    const source = audioContext.createBufferSource();
    this.audioSource = source;
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    source.onended = () => {
      if (this.generation === currentGeneration) this.stop();
    };
    source.start();
    this.update({ cueId, error: null, status: 'playing' });
  }

  private decodeHca(
    bytes: ArrayBuffer,
    currentGeneration: number,
  ): Promise<HcaDecodeSuccessPayload> {
    return new Promise((resolve, reject) => {
      const worker = new Worker(
        new URL('./hca/hca-worker.ts', import.meta.url),
        { name: 'magi-hca-decoder', type: 'module' },
      );
      this.worker = worker;
      this.workerReject = reject;
      const finish = () => {
        worker.terminate();
        if (this.worker === worker) this.worker = null;
        if (this.workerReject === reject) this.workerReject = null;
      };
      worker.onerror = event => {
        finish();
        reject(new Error(event.message || 'HCA 解码器运行失败'));
      };
      worker.onmessage = (event: MessageEvent<HcaDecodeResponse>) => {
        finish();
        if (this.generation !== currentGeneration) {
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        const response = event.data;
        if (!response.ok) {
          reject(new Error(response.error));
          return;
        }
        resolve({
          channels: response.channels,
          sampleRate: response.sampleRate,
        });
      };
      const request: HcaDecodeRequest = {
        id: currentGeneration,
        bytes,
      };
      worker.postMessage(request, [bytes]);
    });
  }
}

interface HcaDecodeSuccessPayload {
  channels: Float32Array<ArrayBuffer>[];
  sampleRate: number;
}

export const voicePlaybackController = new VoicePlaybackController();
