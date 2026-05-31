import type { NextConfig } from "next";

/**
 * Configure the frontend build for containerized standalone deployment.
 */
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
