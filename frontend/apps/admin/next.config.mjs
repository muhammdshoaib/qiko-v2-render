/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["admin.qiko.localhost"],
  reactStrictMode: true,
  transpilePackages: ["@qiko/ui"],
};

export default nextConfig;
