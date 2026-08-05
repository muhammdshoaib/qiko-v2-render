/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["admin.qiko.localhost"],
  // Row 6 of the Essential Living review: `x-powered-by: Next.js` discloses the stack and its
  // version family. The creator app already suppresses it; the admin app was missed.
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@qiko/ui"],
};

export default nextConfig;
