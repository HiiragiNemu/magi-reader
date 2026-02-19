import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'edge';

export async function POST(request: NextRequest) {
  try {
    const { story_id, content, author } = await request.json();

    if (!story_id || !content) {
      return NextResponse.json({ error: '内容为空' }, { status: 400 });
    }

    // @opennextjs/cloudflare 通过 process.env 访问绑定
    const kv = (process.env as any).NEXT_CACHE_WORKERS_KV;

    if (!kv || typeof kv.put !== 'function') {
      // KV 不可用，走备选方案
      console.error('KV 绑定不可用，当前 env keys:', Object.keys(process.env).filter(k => k.includes('NEXT')));
      return NextResponse.json({ error: 'KV 不可用' }, { status: 500 });
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const key = `submit_${story_id}_${timestamp}`;

    await kv.put(key, JSON.stringify({
      story_id,
      content,
      author: author || 'Anonymous',
      submitted_at: new Date().toISOString(),
    }));

    return NextResponse.json({ success: true, key });
  } catch (e) {
    console.error('提交异常:', e);
    return NextResponse.json({ error: '服务器错误' }, { status: 500 });
  }
}

export async function GET() {
  try {
    const kv = (process.env as any).NEXT_CACHE_WORKERS_KV;

    if (!kv || typeof kv.list !== 'function') {
      return NextResponse.json({ error: 'KV 不可用' }, { status: 500 });
    }

    const list = await kv.list({ prefix: 'submit_' });
    const submissions = [];

    for (const key of list.keys) {
      const value = await kv.get(key.name);
      if (value) {
        try {
          submissions.push({ key: key.name, ...JSON.parse(value) });
        } catch {
          submissions.push({ key: key.name, raw: value });
        }
      }
    }

    return NextResponse.json(submissions);
  } catch (e) {
    return NextResponse.json({ error: '查询失败' }, { status: 500 });
  }
}