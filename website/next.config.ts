import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  output: 'export',  // 🔴 强制使用静态导出模式！这能解决 99% 的 Cloudflare 路径问题
  images: {
    unoptimized: true, // 必须加这个，否则 Next.js 的图片优化在静态导出下会报错
  },
};

export default nextConfig;