/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    unoptimized: true,  // 禁用 Next.js 图像优化（resvg WASM 来源），Workers 无需
  },
  experimental: {
    optimizePackageImports: ['lucide-react'],  // 优化图标（可选，减 bundle 大小）
  },
};

module.exports = nextConfig;