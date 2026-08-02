import assert from 'node:assert/strict';
import test from 'node:test';

import { tryExactWikiLocalization } from './exedra-wiki-exact.ts';

test('exact Wiki lookup rejects redirects and carries an abort signal', async () => {
  const originalFetch = globalThis.fetch;
  let redirect: RequestRedirect | undefined;
  let signal: AbortSignal | null | undefined;
  globalThis.fetch = (async (_input: URL | RequestInfo, init?: RequestInit) => {
    redirect = init?.redirect;
    signal = init?.signal;
    return Response.json({
      parse: {
        text: '<table><tr><td>環 いろは</td><td>你好</td></tr></table>',
      },
    });
  }) as typeof fetch;
  try {
    const record = await tryExactWikiLocalization({
      env: {} as CloudflareEnv,
      entry: {
        id: 'exedra_character_character_iroha_test',
        category: 'exedra_character',
        folder: '环彩羽',
        title: '角色剧情',
        game: 'exedra',
        path_cn: '',
        path_jp: '/data/exedra_character/character_iroha/character_iroha_jp.txt',
        source_identity: 'exedra:3_Character:character_iroha',
      },
      jpText: [
        '--- [Section 1] (Source: character_iroha_1.json) ---',
        '環 いろは：こんにちは',
      ].join('\n'),
    });
    assert.equal(record?.provenance, 'exedra_wiki_human');
    assert.match(record?.text ?? '', /環 いろは：你好/u);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(redirect, 'error');
  assert.ok(signal instanceof AbortSignal);
});
