/**
 * /admin/signin — entry point for the GitHub OAuth flow.
 *
 * Server component (Auth.js v5 server action). Clicking the button
 * triggers a server action that calls signIn("github", ...), which
 * redirects to GitHub for OAuth, then back to our callback handler,
 * then back to the original /admin URL.
 */

import { signIn } from "@/auth";

export default function SigninPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; error?: string }>;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-6">
      <div className="w-full max-w-md bg-surface border border-border1 rounded-lg p-8 flex flex-col gap-5">
        <div>
          <div className="font-mono text-[13px] tracking-wider mb-1">
            uxr<span className="text-accent-bright">agent</span>
            <span className="text-textdim ml-2">/ admin</span>
          </div>
          <h1 className="text-textmain text-lg font-medium mb-1">Sign in</h1>
          <p className="text-textmuted text-[13px] leading-relaxed">
            Admin access is locked to the deployment owner. Sign in with the
            GitHub account that matches the <code className="text-accent-bright">OWNER_GITHUB_USER</code>{" "}
            env var on this deployment.
          </p>
        </div>

        <ErrorBlock searchParams={searchParams} />

        <form
          action={async (formData: FormData) => {
            "use server";
            const callbackUrl = (formData.get("callbackUrl") as string) || "/admin";
            await signIn("github", { redirectTo: callbackUrl });
          }}
        >
          <SearchParamsHidden searchParams={searchParams} />
          <button
            type="submit"
            className="w-full px-4 py-2.5 bg-accent border border-accent-bright rounded-md text-textmain font-mono text-[12px] cursor-pointer hover:bg-accent-bright transition"
          >
            Sign in with GitHub
          </button>
        </form>

        <div className="text-textdim text-[11px] font-mono leading-relaxed border-t border-border1 pt-4">
          Wrong GitHub account? Sign out of GitHub in another tab first, then
          come back. The wrong-account guard fires after OAuth completes; you
          will see an error and can retry with the right account.
        </div>
      </div>
    </div>
  );
}

async function ErrorBlock({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  if (!params.error) return null;
  const messages: Record<string, string> = {
    AccessDenied:
      "Access denied. The GitHub account you signed in with does not match this deployment's OWNER_GITHUB_USER allowlist.",
    Configuration:
      "Auth provider not configured. Check that AUTH_GITHUB_ID, AUTH_GITHUB_SECRET, AUTH_SECRET, and OWNER_GITHUB_USER are set in your Vercel project env vars.",
  };
  const msg = messages[params.error] || `Sign-in error: ${params.error}`;
  return (
    <div className="bg-err border border-err-text rounded p-3 text-err-text text-[12px] font-mono leading-relaxed">
      {msg}
    </div>
  );
}

async function SearchParamsHidden({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string }>;
}) {
  const params = await searchParams;
  return (
    <input type="hidden" name="callbackUrl" value={params.callbackUrl || "/admin"} />
  );
}
