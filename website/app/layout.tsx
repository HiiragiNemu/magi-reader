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
        {/* 系统 serif 字体：优雅衬线，阅读沉浸 + antialiased 防锯齿 */}
          <body className="antialiased font-serif">        
            <GlobalProvider>
          {children}
        </GlobalProvider>
      </body>
    </html>
  );
}