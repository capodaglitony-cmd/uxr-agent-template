/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The Modal backend URL is read from MODAL_ENDPOINT at runtime in the
  // server-side API routes; never embedded in the static client bundle.
  // Vercel Hobby tier serves up to 100GB/month bandwidth on free.
};

module.exports = nextConfig;
