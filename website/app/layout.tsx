import type { Metadata } from 'next';
import './globals.css';
import './ui-refinements.css';

import { GlobalProvider } from '@/app/providers';
import CategoryLabelNormalizer from '@/components/CategoryLabelNormalizer';
import ExedraSpeakerNameLocalizer from '@/components/ExedraSpeakerNameLocalizer';

export const metadata: Metadata = {
  title: 'MagiReader',
  description: 'Magia Record Story Archive',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="antialiased font-serif">
        <GlobalProvider>
          <CategoryLabelNormalizer />
          <ExedraSpeakerNameLocalizer />
          {children}
        </GlobalProvider>
      </body>
    </html>
  );
}
