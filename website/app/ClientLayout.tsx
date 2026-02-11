"use client";

import { GlobalProvider } from "@/app/providers";

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  return (
    <GlobalProvider>
      {children}
    </GlobalProvider>
  );
}