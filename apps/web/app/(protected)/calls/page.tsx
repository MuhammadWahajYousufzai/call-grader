import { backendFetch, fmtTs, scoreClass } from "@/lib/backend";
import { Badge, Empty } from "@/components/ui";

export default async function CallsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string>>;
}) {
  const sp = await searchParams;
  const qs = new URLSearchParams({ limit: "50", ...sp }).toString();
  let data = { calls: [] as Array<Record<string, any>> };
  try {
    data = await backendFetch(`/api/calls?${qs}`);
  } catch (e) {
    return <Empty message={`Calls unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  return (
    <div>
      <h1 className="mb-3 text-xl font-semibold">Calls</h1>
      <form className="mb-4 flex flex-wrap gap-2 text-sm" action="/calls">
        <input name="reporting_date" type="date" defaultValue={sp.reporting_date || ""} className="rounded border px-2 py-1" aria-label="Date" />
        <input name="customer" placeholder="Customer number" defaultValue={sp.customer || ""} className="rounded border px-2 py-1" aria-label="Customer" />
        <select name="direction" defaultValue={sp.direction || ""} className="rounded border px-2 py-1" aria-label="Direction">
          <option value="">All directions</option><option>INBOUND</option><option>OUTBOUND</option>
        </select>
        <select name="status" defaultValue={sp.status || ""} className="rounded border px-2 py-1" aria-label="Status">
          <option value="">All statuses</option><option>ANSWERED</option><option>NO_ANSWER</option><option>BUSY</option><option>FAILED</option>
        </select>
        <input name="min_score" placeholder="Min score" defaultValue={sp.min_score || ""} className="w-24 rounded border px-2 py-1" aria-label="Min score" />
        <button className="rounded border px-3 py-1">Filter</button>
      </form>
      {!data.calls.length ? <Empty message="No calls match these filters." /> : (
        <div className="overflow-x-auto rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 text-left">
              <tr><th className="p-2">Time</th><th className="p-2">Customer</th><th className="p-2">Agent</th><th className="p-2">Dir</th><th className="p-2">Status</th><th className="p-2">Score</th><th className="p-2"></th></tr>
            </thead>
            <tbody>
              {data.calls.map((c) => (
                <tr key={c.$id} className="border-t">
                  <td className="p-2">{fmtTs(c.actual_started_at)}</td>
                  <td className="p-2">{c.raw_customer_number}</td>
                  <td className="p-2">{c.agent_name_snapshot}</td>
                  <td className="p-2"><Badge>{c.direction}</Badge></td>
                  <td className="p-2"><Badge>{c.canonical_status}</Badge></td>
                  <td className="p-2">{c.score != null ? <span className={`rounded px-2 py-0.5 ${scoreClass(c.score)}`}>{c.score}</span> : "—"}</td>
                  <td className="p-2"><a className="text-blue-700 hover:underline" href={`/calls/${c.$id}`}>Open</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
