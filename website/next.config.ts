import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  images: {
    unoptimized: true, // 必须加这个，否则 Next.js 的图片优化在静态导出下会报错
  },
  webpack: (config: any) => {  // 用 any 避 TS 内部类型坑（Next.js webpack config 是动态的）
    // 禁用 Node fs（Workers 无 fs API）
    if (!config.resolve) config.resolve = {};
    if (!config.resolve.fallback) config.resolve.fallback = {};
    config.resolve.fallback.fs = false;
    return config;
  },
};

export default nextConfig;