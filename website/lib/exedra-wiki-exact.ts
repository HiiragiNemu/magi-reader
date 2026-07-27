import {
  parseExedraTxt,
  type ExedraStoryEntry,
  type ExedraProvenance,
} from '@/lib/exedra-localization';

const CACHE_PREFIX = 'exedra-localization:v1:';
const WIKI_BASE_DEFAULT = 'https://exedra.wiki';
const MAX_WIKI_BYTES = 8 * 1024 * 1024;

const CHARACTER_WIKI_SLUGS: Record<string, string[]> = {
  character_arina: ['Alina_Gray'],
  character_ashley: ['Ashley_Taylor'],
  character_asuka: ['Asuka_Tatsuki'],
  character_ayame: ['Ayame_Mikuri'],
  character_corbeau: ['Corbeau'],
  character_darc: ['Tart', 'Darc'],
  character_felicia: ['Felicia_Mitsuki'],
  character_fuka: ['Fuka_Higurashi'],
  character_hanna: ['Hanna_Sarasa'],
  character_hazuki: ['Hazuki_Yusa'],
  character_himika: ['Himika_Mao'],
  character_homura: ['Homura_Akemi'],
  character_iroha: ['Iroha_Tamaki'],
  character_kaede: ['Kaede_Akino'],
  character_kako: ['Kako_Natsume'],
  character_kanae: ['Kanae_Yukino'],
  character_karin: ['Karin_Misono'],
  character_kirika: ['Kirika_Kure'],
  character_koito: ['Koito_Asako'],
  character_kokoro: ['Kokoro_Awane'],
  character_konoha: ['Konoha_Shizumi'],
  character_kush: ['Kush_Irnam', 'Kush'],
  character_kyoko: ['Kyoko_Sakura'],
  character_liz: ['Liz_Hawkwood', 'Riz_Hawkwood'],
  character_mabayu: ['Mabayu_Aki'],
  character_madoka: ['Madoka_Kaname'],
  character_mami: ['Mami_Tomoe'],
  character_mannenzakura: ['Rumor_of_the_Ten-Thousand-Year_Sakura'],
  character_masara: ['Masara_Kagami'],
  character_mayoi: ['Mayoi_Hachikuji'],
  character_meiyui: ['Meiyui_Chun'],
  character_melissa: ['Melissa_de_Vignolles', 'Melissa'],
  character_meru: ['Meru_Anna'],
  character_mifuyu: ['Mifuyu_Azusa'],
  character_mitama: ['Mitama_Yakumo'],
  character_mito: ['Mito_Aino'],
  character_momoko: ['Momoko_Togame'],
  character_nagisa: ['Nagisa_Momoe'],
  character_nanaka: ['Nanaka_Tokiwa'],
  character_natsuki: ['Natsuki_Utsuho'],
  character_nemu: ['Nemu_Hiiragi'],
  character_oriko: ['Oriko_Mikuni'],
  character_reira: ['Leila_Ibuki', 'Reira_Ibuki'],
  character_ren: ['Ren_Isuzu'],
  character_rena: ['Rena_Minami'],
  character_rika: ['Rika_Ayano'],
  character_riko: ['Riko_Chiaki'],
  character_sana: ['Sana_Futaba'],
  character_sayaka: ['Sayaka_Miki'],
  character_seika: ['Seika_Kumi'],
  character_senpai: ['Madoka-senpai', 'Madoka_Senpai'],
  character_shinobu: ['Shinobu_Oshino'],
  character_sumire: ['Sumire_Yomeiji'],
  character_touka: ['Touka_Satomi'],
  character_tsukasa: ['Tsukasa_Amane'],
  character_tsukuyo: ['Tsukuyo_Amane'],
  character_tsuruno: ['Tsuruno_Yui'],
  character_ui: ['Ui_Tamaki'],
  character_yachiyo: ['Yachiyo_Nanami'],
  character_yotsugi: ['Yotsugi_Ononoki'],
  character_yuma: ['Yuma_Chitose'],
};

type WikiRecord = {
  version: 1;
  story_id: string;
  source_identity: string;
  provenance: ExedraProvenance;
  source_url: string;
  generated_at: string;
  jp_sha256: string;
  cn_sha256: string;
  text: string;
};

const normalize = (value: string): string =>
  value.replace(/^\uFEFF/u, '').replace(/\r\n?/gu, '\n').replace(/\u0000/gu, '');

export const sha256Text = async (value: string): Promise<string> => {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(normalize(value)),
  );
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
};

const decodeEntities = (value: string): string => value
  .replace(/&nbsp;/giu, ' ')
  .replace(/&amp;/giu, '&')
  .replace(/&lt;/giu, '<')
  .replace(/&gt;/giu, '>')
  .replace(/&quot;/giu, '"')
  .replace(/&#39;|&apos;/giu, "'")
  .replace(/&#(\d+);/gu, (_, code: string) => String.fromCodePoint(Number(code)))
  .replace(/&#x([a-f0-9]+);/giu, (_, code: string) => String.fromCodePoint(Number.parseInt(code, 16)));

const stripHtml = (value: string): string => decodeEntities(value
  .replace(/<br\s*\/?\s*>/giu, '\n')
  .replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>/giu, '')
  .replace(/<[^>]+>/gu, ''))
  .replace(/[\t\f\v ]+/gu, ' ')
  .replace(/\n\s+/gu, '\n')
  .trim();

const tableTexts = (html: string): string[] => {
  const texts: string[] = [];
  for (const rowMatch of html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/giu)) {
    const cells = [...rowMatch[1].matchAll(/<t[dh]\b[^>]*>([\s\S]*?)<\/t[dh]>/giu)]
      .map(match => stripHtml(match[1]))
      .filter(Boolean);
    if (cells.length < 2) continue;
    const headerLike = cells.every(cell => /^(?:角色|人物|姓名|台词|臺詞|文本|中文|日文|Name|Text)$/iu.test(cell));
    if (headerLike) continue;
    const body = cells.at(-1)?.trim() ?? '';
    if (body && body.length <= 20_000 && !/^\d+$/u.test(body)) texts.push(body);
  }
  return texts;
};

const colonTexts = (html: string): string[] => {
  const visible = stripHtml(html
    .replace(/<\/p>|<\/li>|<\/div>|<\/h\d>/giu, '\n'));
  const texts: string[] = [];
  for (const raw of visible.split('\n')) {
    const line = raw.trim();
    const positions = [line.indexOf(':'), line.indexOf('：')]
      .filter(index => index > 0 && index < 160);
    if (!positions.length) continue;
    const body = line.slice(Math.min(...positions) + 1).trim();
    if (body && body.length <= 20_000) texts.push(body);
  }
  return texts;
};

const serializeWithJpSpeakers = (jpText: string, translatedTexts: string[]): string => {
  const sections = parseExedraTxt(jpText);
  const expected = sections.reduce((sum, section) => sum + section.blocks.length, 0);
  if (translatedTexts.length !== expected) {
    throw new Error(`Wiki/JP 文本块数不一致：JP=${expected} Wiki=${translatedTexts.length}`);
  }
  let offset = 0;
  const lines: string[] = [];
  for (const section of sections) {
    lines.push(`--- [Section ${section.number}] (Source: ${section.source}) ---`);
    for (const block of section.blocks) {
      const text = normalize(translatedTexts[offset++] ?? '').trim();
      if (!text) throw new Error('Wiki 中文包含空文本块');
      lines.push(`${block.speaker}：${text}`);
    }
    lines.push('');
  }
  return `${lines.join('\n').trim()}\n`;
};

export const canonicalizeLocalizedSpeakers = (
  jpText: string,
  localizedText: string,
): string => {
  const localized = parseExedraTxt(localizedText);
  const translatedTexts = localized.flatMap(section => section.blocks.map(block => block.text));
  return serializeWithJpSpeakers(jpText, translatedTexts);
};

const groupKey = (entry: ExedraStoryEntry): string =>
  entry.source_identity.split(':').at(-1)?.toLowerCase() ?? '';

const exactTitles = (entry: ExedraStoryEntry): string[] => {
  const slugs = CHARACTER_WIKI_SLUGS[groupKey(entry)] ?? [];
  return slugs.flatMap(slug => [
    `:${slug}/Story/Chinese`,
    `${slug}/Story/Chinese`,
  ]);
};

const readJsonBounded = async (response: Response): Promise<unknown> => {
  if (!response.ok) throw new Error(`Wiki API HTTP ${response.status}`);
  const declared = Number(response.headers.get('content-length'));
  if (Number.isSafeInteger(declared) && declared > MAX_WIKI_BYTES) {
    await response.body?.cancel('Wiki response too large');
    throw new Error('Wiki API 响应过大');
  }
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > MAX_WIKI_BYTES) throw new Error('Wiki API 响应过大');
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) as unknown;
};

const pageHtml = async (base: string, title: string): Promise<string | null> => {
  const api = `${base.replace(/\/$/u, '')}/api.php`;
  const url = new URL(api);
  url.search = new URLSearchParams({
    action: 'parse',
    page: title,
    prop: 'text',
    redirects: '1',
    format: 'json',
    formatversion: '2',
    origin: '*',
  }).toString();
  const value = await readJsonBounded(await fetch(url, { headers: { Accept: 'application/json' } }));
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const parse = (value as { parse?: unknown }).parse;
  if (!parse || typeof parse !== 'object' || Array.isArray(parse)) return null;
  const text = (parse as { text?: unknown }).text;
  if (typeof text === 'string') return text;
  if (text && typeof text === 'object' && !Array.isArray(text)) {
    const legacy = (text as { '*'?: unknown })['*'];
    return typeof legacy === 'string' ? legacy : null;
  }
  return null;
};

export const tryExactWikiLocalization = async ({
  env,
  entry,
  jpText,
}: {
  env: CloudflareEnv;
  entry: ExedraStoryEntry;
  jpText: string;
}): Promise<WikiRecord | null> => {
  if (entry.category !== 'exedra_character') return null;
  const titles = exactTitles(entry);
  if (!titles.length) return null;
  const expected = parseExedraTxt(jpText)
    .reduce((sum, section) => sum + section.blocks.length, 0);
  const base = env.EXEDRA_WIKI_BASE_URL || WIKI_BASE_DEFAULT;
  for (const title of titles) {
    try {
      const html = await pageHtml(base, title);
      if (!html) continue;
      const table = tableTexts(html);
      const colon = colonTexts(html);
      const translated = table.length === expected
        ? table
        : colon.length === expected
          ? colon
          : [];
      if (!translated.length) continue;
      const text = serializeWithJpSpeakers(jpText, translated);
      const record: WikiRecord = {
        version: 1,
        story_id: entry.id,
        source_identity: entry.source_identity,
        provenance: 'exedra_wiki_human',
        source_url: `${base.replace(/\/$/u, '')}/wiki/${encodeURIComponent(title.replace(/ /gu, '_'))}`,
        generated_at: new Date().toISOString(),
        jp_sha256: await sha256Text(jpText),
        cn_sha256: await sha256Text(text),
        text,
      };
      if (env.SUBMISSIONS_KV) {
        await env.SUBMISSIONS_KV.put(`${CACHE_PREFIX}${entry.id}`, JSON.stringify(record));
      }
      return record;
    } catch (error) {
      console.warn('Exact Exedra Wiki page rejected', title, error);
    }
  }
  return null;
};
