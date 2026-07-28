import {
  loadGeneralVoiceManifest,
  loadGeneralVoiceScript,
  type GeneralVoiceLanguage,
  type GeneralVoiceManifest,
  type GeneralVoiceScript,
} from '@/lib/general-voice-source';

const EXPECTED_CN_MODELS = 411;
const MANIFEST_FRESH_MS = 15 * 60 * 1000;
const SCRIPT_FRESH_MS = 60 * 60 * 1000;
const MAX_SCRIPT_CACHE = 32;

type Timed<T> = {
  value: T;
  expiresAt: number;
  lastUsed: number;
};

let manifestCache: Timed<GeneralVoiceManifest> | null = null;
let manifestPending: Promise<GeneralVoiceManifest> | null = null;
const scriptCache = new Map<string, Timed<GeneralVoiceScript>>();
const scriptPending = new Map<string, Promise<GeneralVoiceScript>>();

const validateCurrentManifest = (
  manifest: GeneralVoiceManifest,
): GeneralVoiceManifest => {
  const cnModels = manifest.models.filter(model => model.langs.cn).length;
  if (cnModels !== EXPECTED_CN_MODELS) {
    throw new Error(
      `语音清单中文模型数量异常：期望 ${EXPECTED_CN_MODELS}，实际 ${cnModels}`,
    );
  }
  return manifest;
};

export const loadCachedGeneralVoiceManifest = async () => {
  const now = Date.now();
  if (manifestCache && manifestCache.expiresAt > now) {
    manifestCache.lastUsed = now;
    return manifestCache.value;
  }
  if (!manifestPending) {
    manifestPending = loadGeneralVoiceManifest()
      .then(validateCurrentManifest)
      .then(value => {
        manifestCache = {
          value,
          expiresAt: Date.now() + MANIFEST_FRESH_MS,
          lastUsed: Date.now(),
        };
        return value;
      })
      .catch(error => {
        if (manifestCache) {
          console.warn('语音清单刷新失败，继续使用旧缓存', error);
          manifestCache.lastUsed = Date.now();
          return manifestCache.value;
        }
        throw error;
      })
      .finally(() => {
        manifestPending = null;
      });
  }
  return manifestPending;
};

const trimScriptCache = () => {
  if (scriptCache.size <= MAX_SCRIPT_CACHE) return;
  const oldest = [...scriptCache.entries()]
    .sort((left, right) => left[1].lastUsed - right[1].lastUsed)
    .slice(0, scriptCache.size - MAX_SCRIPT_CACHE);
  for (const [key] of oldest) scriptCache.delete(key);
};

export const loadCachedGeneralVoiceScript = async (
  modelId: string,
  language: GeneralVoiceLanguage = 'cn',
): Promise<GeneralVoiceScript> => {
  const key = `${language}:${modelId}`;
  const now = Date.now();
  const cached = scriptCache.get(key);
  if (cached && cached.expiresAt > now) {
    cached.lastUsed = now;
    return cached.value;
  }
  const pending = scriptPending.get(key);
  if (pending) return pending;

  const request = loadGeneralVoiceScript(modelId, language)
    .then(value => {
      scriptCache.set(key, {
        value,
        expiresAt: Date.now() + SCRIPT_FRESH_MS,
        lastUsed: Date.now(),
      });
      trimScriptCache();
      return value;
    })
    .catch(error => {
      if (cached) {
        console.warn(`${modelId} 语音脚本刷新失败，继续使用旧缓存`, error);
        cached.lastUsed = Date.now();
        return cached.value;
      }
      throw error;
    })
    .finally(() => {
      scriptPending.delete(key);
    });
  scriptPending.set(key, request);
  return request;
};
