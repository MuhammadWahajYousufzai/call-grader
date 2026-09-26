import { backendFetch } from "@/lib/backend";
import { Empty, Section } from "@/components/ui";
import { revalidatePath } from "next/cache";

async function saveAgent(form: FormData) {
  "use server";
  const { backendFetch } = await import("@/lib/backend");
  await backendFetch("/api/admin/agents", {
    method: "POST",
    body: JSON.stringify({
      name: String(form.get("name")),
      jazz_identifier: String(form.get("jazz_identifier") || ""),
      jazz_extension: String(form.get("jazz_extension") || ""),
    }),
  });
  revalidatePath("/settings/agents");
}

export default async function AgentSettings() {
  let data = { agents: [] as Array<any> };
  try {
    data = await backendFetch("/api/agents");
  } catch (e) {
    return <Empty message={`Settings unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  return (
    <div>
      <h1 className="text-xl font-semibold">Agent mapping</h1>
      <p className="text-sm text-slate-500">Map Jazz identifiers/extensions to employees. Historical reports keep name snapshots.</p>
      <Section title="Employees">
        <ul className="divide-y text-sm">{data.agents.map((a) => (
          <li key={a.agent.$id} className="py-2">{a.agent.name} · Jazz: {a.agent.jazz_identifier || "—"} · Ext: {a.agent.jazz_extension || "—"}</li>
        ))}</ul>
      </Section>
      <Section title="Add / update mapping">
        <form action={saveAgent} className="flex flex-wrap gap-2 text-sm">
          <input name="name" placeholder="Name (Saima/Kiran)" required className="rounded border px-2 py-1" aria-label="Name" />
          <input name="jazz_identifier" placeholder="Jazz identifier" className="rounded border px-2 py-1" aria-label="Jazz identifier" />
          <input name="jazz_extension" placeholder="Extension" className="rounded border px-2 py-1" aria-label="Extension" />
          <button className="rounded bg-slate-900 px-3 py-1 text-white">Save</button>
        </form>
      </Section>
    </div>
  );
}
