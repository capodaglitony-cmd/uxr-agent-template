/**
 * auth.ts — Auth.js v5 GitHub provider with single-allowed-user gate.
 *
 * Locks /admin to whichever GitHub handle is set in OWNER_GITHUB_USER.
 * Anyone else who tries to sign in gets bounced — including their own
 * sign-in attempt is rejected at the signIn callback before any session
 * is created.
 */

import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [GitHub],
  callbacks: {
    /**
     * Reject sign-in immediately if the GitHub handle doesn't match the
     * deployer's OWNER_GITHUB_USER env var. The user never gets a
     * session, so all downstream auth() checks see them as logged out.
     */
    async signIn({ profile }) {
      const allowed = process.env.OWNER_GITHUB_USER;
      if (!allowed) {
        // Fail closed: if the deployer didn't configure the allowlist,
        // nobody gets in. Better than silently allowing all GitHub users.
        return false;
      }
      const candidateLogin =
        typeof profile?.login === "string" ? profile.login : "";
      return candidateLogin.toLowerCase() === allowed.toLowerCase();
    },

    /**
     * Pass the GitHub handle through the JWT so the session can carry
     * it to server components. Auth.js doesn't surface profile.login on
     * session.user by default — only name/email/image.
     */
    async jwt({ token, profile }) {
      if (profile && typeof profile.login === "string") {
        token.login = profile.login;
      }
      return token;
    },

    async session({ session, token }) {
      if (session.user && typeof token.login === "string") {
        // Attach the GitHub handle to the session for /admin checks.
        (session.user as { login?: string }).login = token.login;
      }
      return session;
    },
  },
  pages: {
    signIn: "/admin/signin",
  },
});
