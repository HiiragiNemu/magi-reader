"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Theme = 'light' | 'dark' | 'paper' | 'green';

interface GlobalState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  lastCategory: string;
  setLastCategory: (c: string) => void;
}

const GlobalContext = createContext<GlobalState | undefined>(undefined);

export function GlobalProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('paper');
  const [lastCategory, setLastCategory] = useState('main_story');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const savedTheme = localStorage.getItem('magi_theme') as Theme;
    const savedCat = localStorage.getItem('magi_cat');
    if (savedTheme) setThemeState(savedTheme);
    if (savedCat) setLastCategory(savedCat);
    setMounted(true);
  }, []);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem('magi_theme', t);
    
    const root = document.documentElement;
    root.classList.remove('dark');
    if (t === 'dark') root.classList.add('dark');
  };
  
  const setLastCategoryWrapper = (c: string) => {
    setLastCategory(c);
    localStorage.setItem('magi_cat', c);
  };

  if (!mounted) {
    return <div className="min-h-screen bg-[#f3eacb]"></div>;
  }

  return (
    <GlobalContext.Provider value={{ theme, setTheme, lastCategory, setLastCategory: setLastCategoryWrapper }}>
      
      {/* 1. 背景层 */}
      <div className="magi-background" data-bg-theme={theme} />

      {/* 气球效果 */}
      <div className="magi-balloon-rain" />

      {/* 2. 内容层 */}
      <div className={`min-h-screen transition-colors duration-300 relative z-0 bg-transparent
        ${theme === 'dark' ? 'text-gray-200' : ''}
        ${theme === 'light' ? 'text-gray-900' : ''}
        ${theme === 'paper' ? 'text-[#4a3b2a]' : ''}
        ${theme === 'green' ? 'text-[#1b5e20]' : ''}
      `}>
        {children}
      </div>

      {/* 3. 纹理层 */}
      <div className={`magi-texture ${theme === 'dark' ? 'magi-texture-dark' : 'magi-texture-light'}`} />
      
    </GlobalContext.Provider>
  );
}

export const useGlobal = () => {
  const context = useContext(GlobalContext);
  if (!context) throw new Error("useGlobal must be used within GlobalProvider");
  return context;
};