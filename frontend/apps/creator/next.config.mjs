/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["qiko.localhost"],
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@qiko/ui"],
};

export default nextConfig;
