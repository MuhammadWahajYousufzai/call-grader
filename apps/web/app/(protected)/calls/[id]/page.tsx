import { backendFetch, fmtTs, scoreClass } from "@/lib/backend";
import { Badge, Empty, Section } from "@/components/ui";
import { TranscriptWithAudio } from "@/components/TranscriptWithAudio";

export default async function CallDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let data: any;
  try {
    data = await backendFetch(`/api/calls/${id}`);
  } catch (e) {
    return <Empty message={`Call unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  const c = data.call || {};
  const g = data.grade_data || {};
  const terminalAnalysis: Record<string, string> = {
    NO_SPEECH: "The recording contains no intelligible speech, so no grade was assigned.",
    UNGRADABLE: "The transcript has insufficient evidence to assign a reliable grade. The transcript remains available for review.",
    NO_RECORDING: "A recording is unavailable for this call, so it could not be graded.",
    NOT_ELIGIBLE: "This call did not qualify for recording grading.",
  };
  return (
    <div>
      <a href="/calls" className="text-sm text-blue-700 hover:underline">← All calls</a>
      <h1 className="mt-1 text-xl font-semibold">Call — {c.raw_customer_number || "Unknown"}</h1>
      <div className="mt-2 flex flex-wrap gap-2 text-sm">
        <Badge>{c.direction}</Badge><Badge>{c.canonical_status}</Badge>
        <Badge tone="blue">{g.primary_intent || c.pipeline_status}</Badge>
        {g.overall_score != null && <span className={`rounded px-2 py-0.5 font-semibold ${scoreClass(g.overall_score)}`}>{g.overall_score}/10</span>}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
        <div><dt className="text-slate-500">Agent</dt><dd>{c.agent_name_snapshot}</dd></div>
        <div><dt className="text-slate-500">Time</dt><dd>{fmtTs(c.actual_started_at)}</dd></div>
        <div><dt className="text-slate-500">Reporting date</dt><dd>{c.reporting_date}</dd></div>
        <div><dt className="text-slate-500">Duration</dt><dd>{c.duration_seconds}s</dd></div>
        <div><dt className="text-slate-500">Outcome</dt><dd>{g.conversation_outcome || "—"}</dd></div>
        <div><dt className="text-slate-500">Customer history</dt><dd><a className="text-blue-700 hover:underline" href={`/customers/${encodeURIComponent(c.raw_customer_number || "")}`}>View all interactions</a></dd></div>
      </dl>

      <Section title="Analysis">
        <p className="whitespace-pre-wrap text-sm">{g.analysis || terminalAnalysis[c.pipeline_status] || "Grading pending."}</p>
      </Section>

      <Section title="Strengths">
        {!(g.strengths || []).length ? <Empty message="No strengths recorded yet." /> : (
          <ul className="space-y-2 text-sm">{g.strengths.map((s: any, i: number) => (
            <li key={i} className="rounded border p-2"><strong>{s.category}</strong> · {s.evidence}<br /><span className="text-slate-600">{s.explanation}</span></li>
          ))}</ul>
        )}
      </Section>

      <Section title="Mistakes (timestamped evidence)">
        {!(g.mistakes || []).length ? <Empty message="No mistakes recorded." /> : (
          <ul className="space-y-2 text-sm">{g.mistakes.map((m: any, i: number) => (
            <li key={i} className="rounded border p-2">
              <Badge tone={m.severity === "low" ? "slate" : m.severity === "medium" ? "amber" : "red"}>{m.severity}</Badge>
              <span className="ml-2 font-mono text-xs">{m.timestamp_seconds}s · {m.segment_id}</span>
              <p className="mt-1"><strong>What happened:</strong> {m.evidence}</p>
              <p><strong>Why it matters:</strong> {m.explanation}</p>
              <p><strong>How to improve:</strong> {m.better_approach}</p>
              {m.example_response_roman_urdu && <p className="mt-1 rounded bg-emerald-50 p-2"><strong>Better response:</strong> {m.example_response_roman_urdu}</p>}
            </li>
          ))}</ul>
        )}
      </Section>

      <Section title="Coaching">
        <p className="whitespace-pre-wrap text-sm">{g.coaching_summary || "—"}</p>
        <ul className="mt-2 space-y-1 text-sm">{(g.coaching_actions || []).map((a: any, i: number) => (
          <li key={i} className="rounded border p-2">P{a.priority}: {a.action}{a.example_response_roman_urdu && <> — <em>{a.example_response_roman_urdu}</em></>}</li>
        ))}</ul>
      </Section>

      <Section title="Scoring">
        <ul className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
          {Object.entries(g.dimension_scores || {}).map(([k, v]: [string, any]) => (
            <li key={k} className="rounded border p-2"><strong>{k}</strong>: {v.score ?? "N/A"}<br /><span className="text-slate-600">{v.evidence}</span></li>
          ))}
        </ul>
      </Section>

      <Section title="Roman Urdu transcript">
        <TranscriptWithAudio segments={data.segments || []} audioUrl={data.audio_available ? `/api/proxy-audio/${id}` : null} />
      </Section>
    </div>
  );
}
