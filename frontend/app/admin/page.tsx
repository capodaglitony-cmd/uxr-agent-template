/**
 * /admin — owner-only control panel.
 *
 * Server component. The middleware + signIn callback combo guarantees
 * that anyone reaching this page is authenticated as
 * OWNER_GITHUB_USER. We re-check the handle here as belt-and-
 * suspenders so a misconfigured callback can't leak access.
 */

import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";
import { AdminPanel } from "./admin-panel";

export const dynamic = "force-dynamic";

export default async function AdminHome() {
  const session = await auth();
  if (!session?.user) {
    redirect("/admin/signin");
  }

  const allowed = process.env.OWNER_GITHUB_USER;
  const userLogin = (session.user as { login?: string }).login || "";
  if (!allowed || userLogin.toLowerCase() !== allowed.toLowerCase()) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg p-6">
        <div className="w-full max-w-md bg-surface border border-err-text rounded-lg p-8 text-err-text">
          <h1 className="text-lg font-medium mb-2">Forbidden</h1>
          <p className="text-[13px] leading-relaxed font-mono">
            Signed in as <code>{userLogin || "(unknown)"}</code>, but
            OWNER_GITHUB_USER is set to <code>{allowed || "(unset)"}</code>.
            This belt-and-suspenders check fired; sign out and retry with the
            owner account.
          </p>
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/admin/signin" });
            }}
            className="mt-4"
          >
            <button
              type="submit"
              className="px-3.5 py-1.5 bg-transparent border border-border2 rounded text-textmuted font-mono text-[11px] cursor-pointer hover:bg-surface2 hover:text-textmain hover:border-accent transition"
            >
              Sign out
            </button>
          </form>
        </div>
      </div>
    );
  }

  // signOut is wrapped in a server action so the panel can call it
  // without dragging the SessionProvider into client land.
  async function signOutAction() {
    "use server";
    await signOut({ redirectTo: "/admin/signin" });
  }

  return <AdminPanel user={session.user} signOutAction={signOutAction} />;
}
