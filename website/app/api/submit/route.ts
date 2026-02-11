import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  // 1. 接收前端发来的数据
  const data = await request.json();
  
  // 2. 在终端打印出来，证明前端数据发过来了
  console.log("✅ [本地测试] 收到汉化提交:");
  console.log("ID:", data.story_id);
  console.log("内容长度:", data.content.length);
  // console.log("内容:", data.content); // 内容太长，平时注释掉

  // 3. 假装数据库写入成功，返回成功信号
  return NextResponse.json({ success: true });
}