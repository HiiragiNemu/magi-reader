"use client";

import { BookOpen, Leaf, Moon, Sun } from 'lucide-react';

import type { Theme } from '@/app/providers';
import FloatingWindow from '@/components/FloatingWindow';
import ReaderFontSettings from '@/components/ReaderFontSettings';

const THEME_OPTIONS = [
  { key: 'light', label: '明亮', icon: Sun },
  { key: 'paper', label: '纸张', icon: BookOpen },
  { key: 'green', label: '护眼', icon: Leaf },
  { key: 'dark', label: '深色', icon: Moon },
] as const;

export default function SiteSettingsWindow({
  isOpen,
  onClose,
  theme,
  setTheme,
  isExedra,
}: {
  isOpen: boolean;
  onClose: () => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  isExedra: boolean;
}) {
  return (
    <FloatingWindow
      isOpen={isOpen}
      onClose={onClose}
      theme={theme}
      title="字体与站点设置"
      titleId="site-settings-window-title"
      systemLabel="SYS://MAGIREADER.SETTINGS"
      initialOffset={{ x: 118, y: 76 }}
      className="magi-site-settings-window"
      bodyClassName="space-y-3 p-3 sm:p-4"
      footer="设置只保存在当前浏览器"
    >
      <section
        aria-labelledby="site-theme-settings-heading"
        className={`rounded-lg border p-3 ${
          theme === 'dark'
            ? 'border-gray-700 bg-white/5'
            : 'border-stone-300 bg-white/60'
        }`}
      >
        <h3 id="site-theme-settings-heading" className="text-sm font-bold">
          站点主题
        </h3>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {THEME_OPTIONS.map(option => {
            const Icon = option.icon;
            const active = theme === option.key;
            return (
              <button
                key={option.key}
                type="button"
                aria-pressed={active}
                onClick={() => setTheme(option.key)}
                className={`flex min-h-11 items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-xs font-bold transition ${
                  active
                    ? 'border-emerald-500 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                    : 'border-current opacity-60 hover:opacity-100'
                }`}
              >
                <Icon aria-hidden="true" size={14} />
                {option.label}
              </button>
            );
          })}
        </div>
      </section>

      <ReaderFontSettings theme={theme} isExedra={isExedra} />
    </FloatingWindow>
  );
}
