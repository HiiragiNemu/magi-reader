// 只保留一行 runtime 导出
export const runtime = 'edge';

import type { Metadata } from "next";
import "./globals.css";
// 🔴 关键修改：必须使用 @/app/providers，绝对不能用 ./providers
import { GlobalProvider } from "@/app/providers"; 

export const metadata: Metadata = {
  title: "MagiReader",
  description: "Magia Record Story Archive",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh" suppressHydrationWarning>
      {/* 移除 Google 字体，直接使用系统默认字体，解决加载卡顿 */}
      <body className="antialiased font-sans">
        <GlobalProvider>
          {children}
        </GlobalProvider>
      </body>
    </html>
  );
}