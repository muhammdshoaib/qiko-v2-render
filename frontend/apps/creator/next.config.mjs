/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["qiko.localhost"],
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@qiko/ui"],
  async rewrites() {
    const upstream = process.env.API_UPSTREAM?.replace(/\/$/, "");
    if (!upstream) return [];
    return [
      { source: "/api/:path*", destination: `${upstream}/api/:path*` },
      { source: "/health", destination: `${upstream}/health` },
    ];
  },
};

export default nextConfig;
