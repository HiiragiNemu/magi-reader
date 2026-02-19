import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
  },
  serverExternalPackages: ['@vercel/og', 'resvg', 'sharp'],

  experimental: {
    optimizePackageImports: ['lucide-react'],
  },

  // 将环境变量注入到运行时
  env: {
    CF_API_TOKEN: process.env.CF_API_TOKEN || '',
    CF_ACCOUNT_ID: process.env.CF_ACCOUNT_ID || '',
    KV_NAMESPACE_ID: process.env.KV_NAMESPACE_ID || '',
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