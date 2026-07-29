import assert from 'node:assert/strict';
import test from 'node:test';

import {
  contentRangeTotalExceedsLimit,
  createBoundedVoiceStream,
  getMagirecoVoiceUpstreamUrl,
  MAX_VOICE_BYTES,
  normalizeVoiceRange,
  parseBoundedContentLength,
} from '../lib/audio/voice-proxy.ts';

test('constructs the fixed R2 URL from a strict cue only', () => {
  assert.equal(
    getMagirecoVoiceUpstreamUrl('vo_char_3031_00_01').href,
    'https://pub-70a248f1a6fe4ca597e7a10f8b95dfd8.r2.dev/voice/vo_char_3031_00_01_hca.hca',
  );
  assert.throws(
    () => getMagirecoVoiceUpstreamUrl('//evil.invalid/a'),
    /Invalid Magia Record/,
  );
});

test('accepts one bounded byte range and rejects range abuse', () => {
  assert.equal(normalizeVoiceRange(null), null);
  assert.equal(normalizeVoiceRange('bytes=0-1023'), 'bytes=0-1023');
  assert.equal(normalizeVoiceRange('bytes=1024-'), 'bytes=1024-');
  assert.equal(normalizeVoiceRange('bytes=-1024'), 'bytes=-1024');
  assert.equal(normalizeVoiceRange('bytes=20-10'), null);
  assert.equal(normalizeVoiceRange('bytes=0-0,2-2'), null);
  assert.equal(normalizeVoiceRange(`bytes=-${MAX_VOICE_BYTES + 1}`), null);
  assert.equal(
    normalizeVoiceRange(`bytes=0-${MAX_VOICE_BYTES}`),
    null,
  );
});

test('parses only safe decimal Content-Length values', () => {
  assert.equal(parseBoundedContentLength('165744'), 165744);
  assert.equal(parseBoundedContentLength(null), null);
  assert.equal(parseBoundedContentLength('-1'), null);
  assert.equal(parseBoundedContentLength('1e6'), null);
  assert.equal(parseBoundedContentLength('9007199254740992'), null);
});

test('detects an oversized total object in Content-Range', () => {
  assert.equal(
    contentRangeTotalExceedsLimit(`bytes 0-9/${MAX_VOICE_BYTES}`),
    false,
  );
  assert.equal(
    contentRangeTotalExceedsLimit(`bytes 0-9/${MAX_VOICE_BYTES + 1}`),
    true,
  );
  assert.equal(contentRangeTotalExceedsLimit('bytes 0-9/*'), false);
});

test('bounded stream stops before forwarding more than its byte ceiling', async () => {
  const source = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new Uint8Array([1, 2]));
      controller.enqueue(new Uint8Array([3, 4]));
      controller.close();
    },
  });
  const reader = createBoundedVoiceStream(source, 3).getReader();
  assert.deepEqual(Array.from((await reader.read()).value ?? []), [1, 2]);
  await assert.rejects(reader.read(), /Voice object exceeds size limit/);
});
