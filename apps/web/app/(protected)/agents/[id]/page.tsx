import { backendFetch, fmtTs } from "@/lib/backend";
import { Empty, Section, Stat } from "@/components/ui";

export default async function AgentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let data: any;
  try {
    data = await backendFetch(`/api/agents/${id}`);
  } catch (e) {
    return <Empty message={`Agent unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  const m = data.metrics || {};
  return (
    <div>
      <h1 className="text-xl font-semibold">{data.agent?.name}</h1>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Answered" value={m.combined_answered_total ?? 0} />
        <Stat label="Avg score" value={m.average_score ?? "—"} />
        <Stat label="Graded" value={m.calls_graded ?? 0} />
        <Stat label="Orders" value={m.orders_detected ?? 0} />
      </div>
      <Section title="Recent calls">
        {!(data.recent_calls || []).length ? <Empty message="No calls yet." /> : (
          <ul className="divide-y text-sm">{data.recent_calls.map((c: any) => (
            <li key={c.$id} className="flex justify-between py-2">
              <span>{fmtTs(c.actual_started_at)} · {c.direction} · {c.canonical_status}</span>
              <a className="text-blue-700 hover:underline" href={`/calls/${c.$id}`}>Open</a>
            </li>
          ))}</ul>
        )}
      </Section>
    </div>
  );
}
