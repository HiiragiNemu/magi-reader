import { NextResponse } from 'next/server';

export const runtime = 'edge';

export async function POST(request: Request) {
  try {
    const data: any = await request.json();
    const db = (process.env as any).DB;
    if (!db) return NextResponse.json({ error: "DB binding missing" }, { status: 500 });

    await db.prepare(
      "INSERT INTO submissions (story_id, content, author, status) VALUES (?, ?, ?, 'pending')"
    ).bind(data.story_id, data.content, data.author).run();

    return NextResponse.json({ success: true });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}