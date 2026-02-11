import { NextResponse } from 'next/server';

// 🔴 关键：只需声明一次 Edge 运行时
export const runtime = 'edge';

export async function POST(request: Request) {
  try {
    const data: any = await request.json();
    
    // 获取 D1 数据库实例
    // 注意：线上环境下，Cloudflare 绑定的 DB 会挂载在 process.env 下
    const db = (process.env as any).DB;

    if (!db) {
      // 如果没有找到数据库绑定，返回错误
      return NextResponse.json({ error: "Database binding 'DB' not found" }, { status: 500 });
    }

    // 执行数据库插入
    await db.prepare(
      "INSERT INTO submissions (story_id, content, author, status) VALUES (?, ?, ?, 'pending')"
    ).bind(data.story_id, data.content, data.author).run();

    return NextResponse.json({ success: true });
  } catch (err: any) {
    console.error(err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}