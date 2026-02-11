export const runtime = 'edge';
import { NextResponse } from 'next/server';

// 🔴 关键修复：指定 Edge 运行时
export const runtime = 'edge';

export async function POST(request: Request) {
  try {
    const data = await request.json();
    
    // 获取 D1 数据库实例 (在 Edge Runtime 中通过 process.env 获取绑定)
    // 注意：本地开发时 process.env.DB 是 undefined，这代码只能在线上跑通
    const db = process.env.DB as any; 

    if (!db) {
        throw new Error("Database binding not found");
    }

    await db.prepare(
      "INSERT INTO submissions (story_id, content, author, status) VALUES (?, ?, ?, 'pending')"
    ).bind(data.story_id, data.content, data.author).run();

    return NextResponse.json({ success: true });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}