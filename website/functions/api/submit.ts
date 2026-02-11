export async function onRequestPost(context: { request: Request; env: { DB: any } }) {
  const { request, env } = context;
  
  try {
    const data: any = await request.json();
    await env.DB.prepare(
      "INSERT INTO submissions (story_id, content, author, status) VALUES (?, ?, ?, 'pending')"
    ).bind(data.story_id, JSON.stringify(data.content), data.author).run();

    return new Response(JSON.stringify({ success: true }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), { 
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}