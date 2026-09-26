import { backendFetch } from "@/lib/backend";
import { Empty, Section, Stat } from "@/components/ui";

export default async function ReportDetail({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  let data: any;
  try {
    data = await backendFetch(`/api/reports/${date}`);
  } catch (e) {
    return <Empty message={`Report unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  const m = data.metrics || {};
  const out = m.outbound || {};
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">Yousuf Rice · Call Quality Report</p>
      <h1 className="text-2xl font-semibold">{date}</h1>
      <Section title="Telephony overview — outbound only">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Total outbound" value={out.total ?? 0} />
          <Stat label="Answered" value={out.ANSWERED ?? 0} />
          <Stat label="No answer" value={out.NO_ANSWER ?? 0} />
          <Stat label="Busy" value={out.BUSY ?? 0} />
          <Stat label="Other" value={(out.FAILED ?? 0) + (out.CANCELLED ?? 0) + (out.UNKNOWN ?? 0) + (out.OTHER ?? 0)} />
        </div>
      </Section>
      <Section title="Answered outbound by agent">
        <div className="flex flex-wrap gap-2">
          {Object.entries(m.answered_outbound_by_agent || {}).map(([a, n]) => (
            <span key={a} className="rounded border px-3 py-1 text-sm">{a}: <strong>{String(n)}</strong></span>
          ))}
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
          <Stat label="Complaints" value={`${m.complaints ?? 0}`} sub={`${m.resolved_complaints ?? 0} resolved · ${m.unresolved_complaints ?? 0} unresolved`} />
          <Stat label="Orders detected" value={m.orders_detected ?? 0} />
          <Stat label="Follow-ups required" value={m.follow_ups_required ?? 0} />
          <Stat label="High/critical flags" value={m.high_critical_flags ?? 0} />
        </div>
      </Section>
      <Section title="Daily coaching summary">
        <p className="whitespace-pre-wrap text-sm">{data.coaching_summary || (m.still_processing === 0 && m.calls_graded === 0 ? "No graded calls available for this reporting date." : "Pending — generated after AI grading completes.")}</p>
      </Section>
      <Section title="System completeness">
        <p className="text-sm">Recordings missing: {m.recordings_missing ?? 0} · No speech: {m.no_speech_calls ?? 0} · Ungradable: {m.ungradable_calls ?? 0} · Failed jobs: {m.processing_failures ?? 0} · Still processing: {m.still_processing ?? 0}</p>
      </Section>
    </div>
  );
}
