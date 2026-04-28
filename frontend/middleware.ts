/**
 * middleware.ts — gate /admin behind Auth.js sign-in.
 *
 * Unauthenticated requests to /admin or /admin/* get redirected to
 * /admin/signin (which then bounces to the GitHub OAuth flow).
 * Note: this only enforces "is signed in" — the OWNER_GITHUB_USER
 * allowlist check happens in auth.ts's signIn callback, so a wrong
 * GitHub user never gets a session in the first place.
 */

import { auth } from "@/auth";

export default auth((req) => {
  if (req.nextUrl.pathname.startsWith("/admin") && !req.auth) {
    const signinUrl = new URL("/admin/signin", req.nextUrl.origin);
    signinUrl.searchParams.set("callbackUrl", req.nextUrl.pathname);
    return Response.redirect(signinUrl);
  }
});

export const config = {
  // Run on /admin and any subpath, but skip the signin page itself
  // (otherwise we get a redirect loop) and the auth API routes.
  matcher: [
    "/admin",
    "/admin/((?!signin).*)",
  ],
};
