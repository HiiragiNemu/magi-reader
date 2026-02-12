import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  images: {
    unoptimized: true, // 必须加这个，否则 Next.js 的图片优化在静态导出下会报错
  },
};

export default nextConfig;