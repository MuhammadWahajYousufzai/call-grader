import { backendFetch } from "@/lib/backend";
import { Empty, Section } from "@/components/ui";

export default async function ReportsPage() {
  let data = { reports: [] as Array<Record<string, string>> };
  try {
    data = await backendFetch("/api/reports");
  } catch (e) {
    return <Empty message={`Reports unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  return (
    <div>
      <h1 className="text-xl font-semibold">Daily reports</h1>
      <Section title="All reports">
        {!data.reports.length ? <Empty message="No reports yet." /> : (
          <ul className="divide-y">
            {data.reports.map((r) => (
              <li key={r.$id} className="flex justify-between py-2 text-sm">
                <span>{r.reporting_date} · {r.status}</span>
                <a className="text-blue-700 hover:underline" href={`/reports/${r.reporting_date}`}>Open</a>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
