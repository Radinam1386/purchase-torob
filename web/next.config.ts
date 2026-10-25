import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  poweredByHeader: false,
  devIndicators: false,
  async rewrites() {
    // 127.0.0.1 on purpose: uvicorn binds IPv4 only, and `localhost` may resolve to ::1 first.
    const apiOrigin = process.env.AGENT_API_INTERNAL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
