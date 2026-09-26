import { backendFetch, fmtTs } from "@/lib/backend";
import { Empty, Section } from "@/components/ui";

export default async function CustomerPage({ params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  const decoded = decodeURIComponent(number);
  let data: any;
  try {
    data = await backendFetch(`/api/customers/${encodeURIComponent(decoded)}/calls`);
  } catch (e) {
    return <Empty message={`Customer history unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  return (
    <div>
      <h1 className="text-xl font-semibold">Customer — {decoded}</h1>
      <p className="text-sm text-slate-500">{data.calls?.length || 0} interactions</p>
      <Section title="Interaction history">
        {!(data.calls || []).length ? <Empty message="No calls for this customer." /> : (
          <ul className="divide-y text-sm">{data.calls.map((c: any) => (
            <li key={c.$id} className="flex justify-between py-2">
              <span>{fmtTs(c.actual_started_at)} · {c.agent_name_snapshot} · {c.direction} · {c.canonical_status} · {c.pipeline_status}</span>
              <a className="text-blue-700 hover:underline" href={`/calls/${c.$id}`}>Open</a>
            </li>
          ))}</ul>
        )}
      </Section>
    </div>
  );
}
