import { NextRequest, NextResponse } from 'next/server';

// 不要写 export const runtime = 'edge'; ← 这就是导致报错的原因

export async function POST(request: NextRequest) {
  try {
    const { story_id, content, author } = await request.json();

    if (!story_id || !content) {
      return NextResponse.json({ error: '内容为空' }, { status: 400 });
    }

    // 通过 process.env 访问 KV 绑定
    const kv = (process.env as any).NEXT_CACHE_WORKERS_KV;

    if (kv && typeof kv.put === 'function') {
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const key = `submit_${story_id}_${timestamp}`;

      await kv.put(key, JSON.stringify({
        story_id,
        content,
        author: author || 'Anonymous',
        submitted_at: new Date().toISOString(),
      }));

      return NextResponse.json({ success: true, key });
    }

    // KV 不可用时的备选：返回错误让前端走降级方案
    console.error('KV 绑定不可用');
    return NextResponse.json({ error: 'KV 不可用' }, { status: 500 });

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