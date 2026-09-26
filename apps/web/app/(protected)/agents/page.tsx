import { backendFetch } from "@/lib/backend";
import { Empty } from "@/components/ui";

export default async function AgentsPage() {
  let data = { agents: [] as Array<any> };
  try {
    data = await backendFetch("/api/agents");
  } catch (e) {
    return <Empty message={`Agents unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  return (
    <div>
      <h1 className="mb-3 text-xl font-semibold">Agents</h1>
      <div className="grid gap-3 md:grid-cols-2">
        {data.agents.map((a) => (
          <a key={a.agent.$id} href={`/agents/${a.agent.$id}`} className="rounded-lg border bg-white p-4 hover:shadow">
            <div className="font-semibold">{a.agent.name}</div>
            <div className="text-sm text-slate-600">Answered: {a.total_answered} · Avg: {a.avg_score} · Graded: {a.calls_graded}</div>
          </a>
        ))}
      </div>
    </div>
  );
}
