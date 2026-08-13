import { NextResponse } from 'next/server';
import { getCloudflareContext } from '@opennextjs/cloudflare';

import { sourceUnverifiedSystemSummary } from '@/lib/machine-translation-review';

const NO_STORE_HEADERS = { 'Cache-Control': 'no-store' };

export async function GET() {
  try {
    const { env } = await getCloudflareContext({ async: true });
    const status = await sourceUnverifiedSystemSummary(env.SUBMISSIONS_KV);
    return NextResponse.json(
      {
        version: 1,
        ...status,
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error) {
    console.error('Failed to read Magia Record source-review state', error);
    return NextResponse.json(
      { error: '魔法纪录来源待核验状态暂时不可用' },
      { status: 500, headers: NO_STORE_HEADERS },
    );
  }
}
