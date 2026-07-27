import { NextRequest, NextResponse } from 'next/server';

import storyIndexJson from './public/story_index.json';
import searchManifestJson from './public/search_index_manifest.json';
import {
  generalVoiceCatalogEntries,
  generalVoiceScriptToTxt,
  loadGeneralVoiceManifest,
  loadGeneralVoiceScript,
} from './lib/general-voice-source';

const VOICE_DATA_RE =
  /^\/data\/general_voice\/(\d{6})\/\1_cn\.(txt|json)$/u;
const MAX_COMBINED_ENTRIES = 100_000;

const jsonHeaders = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'public, max-age=300, stale-while-revalidate=3600',
  'X-Content-Type-Options': 'nosniff',
};

const textHeaders = {
  'Content-Type': 'text/plain; charset=utf-8',
  'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400',
  'X-Content-Type-Options': 'nosniff',
};

const toHex = (buffer: ArrayBuffer): string =>
  Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('');

const combinedIndex = async () => {
  const manifest = await loadGeneralVoiceManifest();
  const voiceEntries = generalVoiceCatalogEntries(manifest);
  const base = Array.isArray(storyIndexJson) ? storyIndexJson : [];
  if (base.length + voiceEntries.length > MAX_COMBINED_ENTRIES) {
    throw new Error('合并剧情目录超过安全上限');
  }
  const ids = new Set(base.map(item => String((item as { id?: unknown }).id ?? '').toLowerCase()));
  for (const entry of voiceEntries) {
    if (ids.has(entry.id.toLowerCase())) throw new Error(`语音剧情编号冲突：${entry.id}`);
    ids.add(entry.id.toLowerCase());
  }
  return [...base, ...voiceEntries];
};

const combinedIndexPayload = async () => {
  const payload = JSON.stringify(await combinedIndex());
  const bytes = new TextEncoder().encode(payload);
  const sha256 = toHex(await crypto.subtle.digest('SHA-256', bytes));
  return { payload, sha256 };
};

const voiceResponse = async (modelId: string, extension: string): Promise<Response> => {
  const [manifest, script] = await Promise.all([
    loadGeneralVoiceManifest(),
    loadGeneralVoiceScript(modelId, 'cn'),
  ]);
  const model = manifest.models.find(item => item.id === modelId && item.langs.cn);
  if (!model) return new Response('没有找到对应的中文语音脚本。', { status: 404, headers: textHeaders });
  if (extension === 'json') {
    return new Response(JSON.stringify(script), { status: 200, headers: jsonHeaders });
  }
  return new Response(generalVoiceScriptToTxt(script, model), {
    status: 200,
    headers: textHeaders,
  });
};

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  try {
    if (pathname === '/') {
      return NextResponse.rewrite(new URL('/voice-home', request.url));
    }
    if (pathname === '/story_index.json') {
      const { payload } = await combinedIndexPayload();
      return new Response(payload, { status: 200, headers: jsonHeaders });
    }
    if (pathname === '/search_index_manifest.json') {
      const { sha256 } = await combinedIndexPayload();
      return Response.json(
        { ...searchManifestJson, story_index_sha256: sha256 },
        { headers: jsonHeaders },
      );
    }
    const voiceMatch = pathname.match(VOICE_DATA_RE);
    if (voiceMatch) return await voiceResponse(voiceMatch[1], voiceMatch[2]);
    return NextResponse.next();
  } catch (error) {
    console.error('General voice proxy failed', error);
    const message = error instanceof Error ? error.message : '语音数据服务暂时不可用';
    return new Response(message, { status: 502, headers: textHeaders });
  }
}

export const config = {
  matcher: [
    '/',
    '/story_index.json',
    '/search_index_manifest.json',
    '/data/general_voice/:path*',
  ],
};
