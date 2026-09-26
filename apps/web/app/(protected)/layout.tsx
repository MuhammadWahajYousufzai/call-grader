import { redirect } from "next/navigation";
import { AuthError, requireAdmin } from "@/lib/auth";

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  let user;
  try { user = await requireAdmin(); }
  catch (error) {
    if (error instanceof AuthError && error.status < 500) redirect(`/login${error.status === 403 ? "?error=forbidden" : ""}`);
    return <main className="mx-auto max-w-md p-8"><h1 className="text-xl font-semibold">Access verification unavailable</h1><p className="mt-3 text-slate-600">Please try again shortly.</p></main>;
  }
  return <>
    <header className="border-b bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <a href="/dashboard" className="font-semibold">Yousuf Rice <span className="font-normal text-slate-500">· Call Grader</span></a>
        <nav className="flex flex-wrap items-center gap-4 text-sm" aria-label="Primary">
          <a href="/dashboard" className="hover:underline">Dashboard</a><a href="/reports" className="hover:underline">Reports</a><a href="/calls" className="hover:underline">Calls</a><a href="/agents" className="hover:underline">Agents</a><a href="/system" className="hover:underline">System</a>
          <form action="/api/auth/logout" method="post"><button className="rounded border px-3 py-1">Sign out</button></form>
        </nav>
      </div>
    </header>
    <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
  </>;
}
