import type { NextConfig } from 'next';
import { initOpenNextCloudflareForDev } from '@opennextjs/cloudflare';

initOpenNextCloudflareForDev();

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
  },
  serverExternalPackages: ['@vercel/og', 'resvg', 'sharp'],

  experimental: {
    optimizePackageImports: ['lucide-react'],
  },

  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      '@vercel/og': false,
      'resvg': false,
      'sharp': false,
      'yoga-wasm-web': false,
    };
    return config;
  },
};

export default nextConfig;
