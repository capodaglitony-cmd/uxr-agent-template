// Auth.js v5 universal handler for sign-in / callback / sign-out.
// All OAuth round-trips land here: /api/auth/signin, /api/auth/signout,
// /api/auth/callback/github, /api/auth/session, etc.

import { handlers } from "@/auth";

export const { GET, POST } = handlers;
