import { NextRequest, NextResponse } from 'next/server';

const CF_API_TOKEN = process.env.CF_API_TOKEN || '';
const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID || '';
const KV_NAMESPACE_ID = process.env.KV_NAMESPACE_ID || '';

const KV_BASE = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}`;

async function kvPut(key: string, value: string) {
  const formData = new FormData();
  formData.append('value', value);
  formData.append('metadata', JSON.stringify({}));

  const res = await fetch(`${KV_BASE}/values/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${CF_API_TOKEN}`,
    },
    body: formData,
  });

  return res.ok;
}

async function kvList(prefix: string) {
  const res = await fetch(`${KV_BASE}/keys?prefix=${encodeURIComponent(prefix)}&limit=100`, {
    headers: {
      'Authorization': `Bearer ${CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
  });

  if (!res.ok) return [];
  const data = await res.json();
  return data.result || [];
}

async function kvGet(key: string) {
  const res = await fetch(`${KV_BASE}/values/${encodeURIComponent(key)}`, {
    headers: {
      'Authorization': `Bearer ${CF_API_TOKEN}`,
    },
  });

  if (!res.ok) return null;
  return await res.text();
}

export async function POST(request: NextRequest) {
  try {
    const { story_id, content, author } = await request.json();

    if (!story_id || !content) {
      return NextResponse.json({ error: '内容为空' }, { status: 400 });
    }

    if (!CF_API_TOKEN || !CF_ACCOUNT_ID || !KV_NAMESPACE_ID) {
      return NextResponse.json({ 
        error: '服务端配置缺失',
        debug: {
          hasToken: !!CF_API_TOKEN,
          hasAccount: !!CF_ACCOUNT_ID,
          hasKV: !!KV_NAMESPACE_ID,
        }
      }, { status: 500 });
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const key = `submit_${story_id}_${timestamp}`;

    const data = JSON.stringify({
      story_id,
      content,
      author: author || 'Anonymous',
      submitted_at: new Date().toISOString(),
    });

    const success = await kvPut(key, data);

    if (success) {
      return NextResponse.json({ success: true, key });
    } else {
      return NextResponse.json({ error: 'KV 写入失败' }, { status: 500 });
    }
  } catch (e: any) {
    return NextResponse.json({ 
      error: '服务器错误', 
      message: e?.message 
    }, { status: 500 });
  }
}

export async function GET() {
  try {
    if (!CF_API_TOKEN || !CF_ACCOUNT_ID || !KV_NAMESPACE_ID) {
      return NextResponse.json({ 
        error: '配置缺失',
        debug: {
          hasToken: !!CF_API_TOKEN,
          hasAccount: !!CF_ACCOUNT_ID,
          hasKV: !!KV_NAMESPACE_ID,
        }
      }, { status: 500 });
    }

    const keys = await kvList('submit_');
    const submissions = [];

    for (const keyObj of keys) {
      const value = await kvGet(keyObj.name);
      if (value) {
        try {
          submissions.push({ key: keyObj.name, ...JSON.parse(value) });
        } catch {
          submissions.push({ key: keyObj.name, raw: value });
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