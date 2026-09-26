import { backendFetch, fmtTs } from "@/lib/backend";
import { Empty, Section } from "@/components/ui";
import { revalidatePath } from "next/cache";

async function trigger(path: string) {
  "use server";
  const { backendFetch } = await import("@/lib/backend");
  await backendFetch(path, { method: "POST" });
  revalidatePath("/system");
}

export default async function SystemPage() {
  let data: any;
  try {
    data = await backendFetch("/api/system/status");
  } catch (e) {
    return <Empty message={`System status unavailable — backend offline? (${e instanceof Error ? e.message : e})`} />;
  }
  return (
    <div>
      <h1 className="text-xl font-semibold">System / automation health</h1>
      <Section title="Jazz connectivity">
        <dl className="grid grid-cols-1 gap-2 text-sm md:grid-cols-3">
          <div><dt className="text-slate-500">Last verified Jazz session</dt><dd>{data.last_login ? fmtTs(data.last_login) : "—"}</dd></div>
          <div><dt className="text-slate-500">Last successful sync</dt><dd>{data.last_sync ? fmtTs(data.last_sync) : "—"}</dd></div>
          <div><dt className="text-slate-500">Next scheduled sync</dt><dd>{data.next_scheduled_sync}</dd></div>
        </dl>
      </Section>
      <Section title="Pipeline">
        <p className="text-sm">Backlog: {data.backlog} · Failed jobs: {data.failed_jobs?.length || 0}</p>
        {!!data.failed_jobs?.length && (
          <ul className="mt-2 divide-y text-sm">{data.failed_jobs.map((j: any) => (
            <li key={j.$id} className="py-1">{j.job_type} · {j.call_id} · {j.last_error?.slice(0, 120)}</li>
          ))}</ul>
        )}
      </Section>
      <Section title="Recent ingestion runs">
        <ul className="divide-y text-sm">{(data.recent_runs || []).map((r: any) => (
          <li key={r.$id} className="py-1">{fmtTs(r.started_at)} · {r.status} · discovered {r.calls_discovered} {r.error_message ? `· ${r.error_message.slice(0, 120)}` : ""}</li>
        ))}</ul>
      </Section>
      <Section title="Admin controls (audit logged)">
        <div className="flex flex-wrap gap-2 text-sm">
          <form action={trigger.bind(null, "/api/admin/jazz/sync")}><button className="rounded border px-3 py-1">Sync Jazz now</button></form>
        </div>
        <p className="mt-2 text-xs text-slate-500">Retry / re-transcribe / re-grade / regenerate-report controls live on the relevant call &amp; report rows via the API.</p>
      </Section>
    </div>
  );
}
