import { backendFetch, fmtTs } from "@/lib/backend";
import { Badge, Stat, Section, Empty } from "@/components/ui";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  let data: { reporting_date: string; metrics: Record<string, unknown>; attention: Array<Record<string, string>>; system_alert?: string };
  try {
    data = await backendFetch(`/api/dashboard${date ? `?reporting_date=${date}` : ""}`);
  } catch (e) {
    return <Empty message={`Dashboard unavailable — is the backend running? (${e instanceof Error ? e.message : e})`} />;
  }
  const m = data.metrics as Record<string, any>;
  const out = m.outbound || {};
  return (
    <div>
      {data.system_alert && <div role="alert" className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm font-medium text-red-900">{data.system_alert} · See System for details.</div>}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard — {data.reporting_date}</h1>
        <form className="flex gap-2 text-sm" action="/dashboard">
          <input type="date" name="date" defaultValue={data.reporting_date} className="rounded border px-2 py-1" aria-label="Report date" />
          <button className="rounded border px-3 py-1">View</button>
        </form>
      </div>

      <Section title="Telephony overview — outbound only">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Total outbound" value={out.total ?? 0} />
          <Stat label="Answered" value={out.ANSWERED ?? 0} />
          <Stat label="No answer" value={out.NO_ANSWER ?? 0} />
          <Stat label="Busy" value={out.BUSY ?? 0} />
          <Stat label="Other" value={(out.FAILED ?? 0) + (out.CANCELLED ?? 0) + (out.UNKNOWN ?? 0) + (out.OTHER ?? 0)} />
        </div>
      </Section>

      <Section title="Combined answered/eligible — inbound + outbound">
        <div className="flex flex-wrap gap-2">
          {Object.entries(m.combined_answered_by_agent || {}).map(([a, n]) => (
            <span key={a} className="rounded border px-3 py-1 text-sm">{a}: <strong>{String(n)}</strong></span>
          ))}
          <span className="rounded bg-slate-900 px-3 py-1 text-sm text-white">Total: {String(m.combined_answered_total ?? 0)}</span>
        </div>
      </Section>

      <Section title="Quality overview">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Calls graded" value={m.calls_graded ?? 0} />
          <Stat label="Average score" value={m.average_score ?? "—"} />
          <Stat label="Low-score calls" value={m.low_score_calls ?? 0} />
          <Stat label="Complaints" value={`${m.complaints ?? 0} (${m.resolved_complaints ?? 0} resolved)`} />
          <Stat label="Orders detected" value={m.orders_detected ?? 0} />
          <Stat label="Follow-ups" value={m.follow_ups_required ?? 0} />
          <Stat label="High/critical flags" value={m.high_critical_flags ?? 0} />
          <Stat label="Still processing" value={m.still_processing ?? 0} />
          <Stat label="No speech" value={m.no_speech_calls ?? 0} />
          <Stat label="Ungradable" value={m.ungradable_calls ?? 0} />
        </div>
      </Section>

      <Section title="Calls requiring attention">
        {!data.attention?.length ? (
          <Empty message="No low-score or flagged calls." />
        ) : (
          <ul className="divide-y">
            {data.attention.map((c) => (
              <li key={c.$id} className="flex items-center justify-between py-2 text-sm">
                <span>{c.customer} · {c.agent} · {c.status}</span>
                <a className="text-blue-700 hover:underline" href={`/calls/${c.$id}`}>Inspect</a>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <p className="mt-4 text-xs text-slate-400">Fetched {fmtTs(new Date().toISOString())} PKT view · backend-driven metrics (never LLM-counted).</p>
    </div>
  );
}
