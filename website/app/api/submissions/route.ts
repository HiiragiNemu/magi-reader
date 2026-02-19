import { getCloudflareContext } from "@opennextjs/cloudflare";

export async function GET() {
  try {
    const { env } = await getCloudflareContext();
    const list = await (env as any).SUBMISSIONS.list();
    
    const submissions = await Promise.all(
      list.keys.map(async (key: any) => {
        const value = await (env as any).SUBMISSIONS.get(key.name);
        return { key: key.name, ...JSON.parse(value || "{}") };
      })
    );

    return new Response(
      JSON.stringify(submissions), 
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (e: any) {
    return new Response(
      JSON.stringify({ error: e.message }), 
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}