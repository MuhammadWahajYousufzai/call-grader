import { backendFetch } from "@/lib/backend";
import { Empty, Section } from "@/components/ui";
import { revalidatePath } from "next/cache";

async function saveRule(form: FormData) {
  "use server";
  const { backendFetch } = await import("@/lib/backend");
  await backendFetch("/api/admin/rules", {
    method: "POST",
    body: JSON.stringify({ key: String(form.get("key")), value: String(form.get("value")) }),
  });
  revalidatePath("/settings/business-rules");
}

export default async function RulesPage() {
  let data = { rules: [] as Array<any> };
  try {
    data = await backendFetch("/api/admin/rules");
  } catch (e) {
    return <Empty message={`Rules unavailable (${e instanceof Error ? e.message : e})`} />;
  }
  return (
    <div>
      <h1 className="text-xl font-semibold">Business rules / knowledge base</h1>
      <p className="text-sm text-slate-500">Authoritative facts the grader compares against. When silent, accuracy is “not_verifiable” — never a penalty.</p>
      <Section title="Current rules">
        <ul className="space-y-2 text-sm">{data.rules.map((r) => (
          <li key={r.$id} className="rounded border p-2"><strong>{r.key}</strong> (v{r.version})<br />{r.value}</li>
        ))}</ul>
      </Section>
      <Section title="Add / update rule">
        <form action={saveRule} className="flex flex-col gap-2 text-sm">
          <input name="key" placeholder="key (e.g. prices)" required className="rounded border px-2 py-1" aria-label="Key" />
          <textarea name="value" placeholder="Authoritative value…" required rows={4} className="rounded border px-2 py-1" aria-label="Value" />
          <button className="w-fit rounded bg-slate-900 px-3 py-1 text-white">Save rule</button>
        </form>
      </Section>
    </div>
  );
}
