import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
  },
  // 修正 1: 在 Next.js 16 中，这个配置移到了最外层
  serverExternalPackages: ['@vercel/og', 'resvg', 'sharp'],
  
  experimental: {
    optimizePackageImports: ['lucide-react'],
  },

  // 修正 2: 强力屏蔽 Webpack 依赖
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