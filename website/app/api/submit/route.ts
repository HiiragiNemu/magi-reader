import { getCloudflareContext } from "@opennextjs/cloudflare";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    
    if (!body.story_id || !body.content) {
      return new Response(
        JSON.stringify({ error: "缺少必要字段" }), 
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    const { env } = await getCloudflareContext();
    
    const key = `${body.story_id}_${Date.now()}`;
    const data = {
      story_id: body.story_id,
      content: body.content,
      author: body.author || "Anonymous",
      created_at: new Date().toISOString(),
    };

    await (env as any).SUBMISSIONS.put(key, JSON.stringify(data));

    return new Response(
      JSON.stringify({ success: true }), 
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  } catch (e: any) {
    console.error("Submit error:", e);
    return new Response(
      JSON.stringify({ error: e.message || "服务器错误" }), 
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}