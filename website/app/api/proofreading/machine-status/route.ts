import { NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { machineTranslationSystemSummary } from '@/lib/machine-translation-review';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };

export async function GET() {
  try {
    const { env } = await getCloudflareContext({ async: true });
    const [magireco, exedra] = await Promise.all([
      machineTranslationSystemSummary(env.SUBMISSIONS_KV, 'magireco'),
      machineTranslationSystemSummary(env.SUBMISSIONS_KV, 'exedra'),
    ]);
    return NextResponse.json(
      {
        version: 2,
        systems: { magireco, exedra },
        // Backward compatibility for clients deployed before game separation.
        ...magireco,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error) {
    console.error('Failed to read machine translation review state', error);
    return NextResponse.json(
      { error: '机器翻译人工校验状态暂时不可用' },
      { status: 500, headers: NO_STORE_HEADERS },
    );
  }
}
