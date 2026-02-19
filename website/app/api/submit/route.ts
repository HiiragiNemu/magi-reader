import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const { story_id, content, author } = await request.json();

    if (!story_id || !content) {
      return NextResponse.json({ error: '内容为空' }, { status: 400 });
    }

    // 尝试多种方式获取 KV
    let kv: any = null;

    // 方式1: process.env（opennextjs/cloudflare 标准方式）
    if ((process.env as any).NEXT_CACHE_WORKERS_KV?.put) {
      kv = (process.env as any).NEXT_CACHE_WORKERS_KV;
    }

    // 方式2: globalThis（某些版本）
    if (!kv && (globalThis as any).NEXT_CACHE_WORKERS_KV?.put) {
      kv = (globalThis as any).NEXT_CACHE_WORKERS_KV;
    }

    // 方式3: 通过 request 上下文
    if (!kv) {
      try {
        const ctx = (request as any).cf || (request as any).context;
        if (ctx?.env?.NEXT_CACHE_WORKERS_KV?.put) {
          kv = ctx.env.NEXT_CACHE_WORKERS_KV;
        }
      } catch {}
    }

    if (kv) {
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

    // KV 都获取不到，返回调试信息
    return NextResponse.json({ 
      error: 'KV 不可用',
      debug: {
        processEnvKeys: Object.keys(process.env).filter(k => 
          k.includes('KV') || k.includes('CACHE') || k.includes('NEXT')
        ),
        hasGlobalKV: !!(globalThis as any).NEXT_CACHE_WORKERS_KV,
      }
    }, { status: 500 });

  } catch (e: any) {
    return NextResponse.json({ 
      error: '服务器错误', 
      message: e?.message 
    }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    let kv: any = null;

    if ((process.env as any).NEXT_CACHE_WORKERS_KV?.list) {
      kv = (process.env as any).NEXT_CACHE_WORKERS_KV;
    }
    if (!kv && (globalThis as any).NEXT_CACHE_WORKERS_KV?.list) {
      kv = (globalThis as any).NEXT_CACHE_WORKERS_KV;
    }
    if (!kv) {
      try {
        const ctx = (request as any).cf || (request as any).context;
        if (ctx?.env?.NEXT_CACHE_WORKERS_KV?.list) {
          kv = ctx.env.NEXT_CACHE_WORKERS_KV;
        }
      } catch {}
    }

    if (!kv) {
      return NextResponse.json({ 
        error: 'KV 不可用',
        hint: '请在 Cloudflare Dashboard 检查 KV 绑定配置'
      }, { status: 500 });
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
  } catch (e: any) {
    return NextResponse.json({ 
      error: '查询失败', 
      message: e?.message 
    }, { status: 500 });
  }
}