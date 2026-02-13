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
  // 用 mounted 避免 hydration mismatch
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
    
    // 更新 HTML class 以支持 Tailwind 的 dark 模式选择器
    const root = document.documentElement;
    root.classList.remove('dark');
    if (t === 'dark') root.classList.add('dark');
  };
  
  const setLastCategoryWrapper = (c: string) => {
    setLastCategory(c);
    localStorage.setItem('magi_cat', c);
  };

  // 防止服务端渲染和客户端不一致导致的闪烁
  if (!mounted) {
    return <div className="min-h-screen bg-[#f3eacb]"></div>;
  }

  return (
    <GlobalContext.Provider value={{ theme, setTheme, lastCategory, setLastCategory: setLastCategoryWrapper }}>
      {/* 
         结构说明：
         1. 背景层 (div.magi-background): 负责颜色 + 气球动画，位于 z-index: -50
         2. 内容层 (div.relative): 正常的页面内容，背景必须透明！
         3. 纹理层 (div.magi-texture): 负责纸张质感，位于 z-index: 9999, pointer-events: none
      */}
      
      {/* 1. 背景层：根据 theme 设置 data-bg-theme 属性，触发 CSS 中的背景色切换 */}
      <div className="magi-background" data-bg-theme={theme} />
      
  <GlobalContext.Provider value={{ theme, setTheme, lastCategory, setLastCategory: setLastCategoryWrapper }}>
    
    {/* 1. 高度模糊底层背景 */}
    <div className="magi-background" data-bg-theme={theme} />

    {/* --- 修改此处：将之前的 magi-sharp-rain 替换为真实气球效果 --- */}
    <div className="magi-balloon-rain" />
    {/* --- 修改结束 --- */}

    {/* 2. 内容层 */}
    <div className={`min-h-screen transition-colors duration-300 relative z-0 bg-transparent ...`}>
      {children}
    </div>

    {/* 3. 羊皮纸纹理滤镜 */}
    <div className={`magi-texture ${theme === 'dark' ? 'magi-texture-dark' : 'magi-texture-light'}`} />
    
  </GlobalContext.Provider>
);
      {/* 2. 内容层：注意 text-color 的设置，但不要设置 bg-color */}
      <div className={`min-h-screen transition-colors duration-300 relative z-0
        ${theme === 'dark' ? 'text-gray-200' : ''}
        ${theme === 'light' ? 'text-gray-900' : ''}
        ${theme === 'paper' ? 'text-[#4a3b2a]' : ''}
        ${theme === 'green' ? 'text-[#1b5e20]' : ''}
      `}>
        {children}
      </div>

      {/* 3. 纹理层：全覆盖 */}
      <div className={`magi-texture ${theme === 'dark' ? 'magi-texture-dark' : 'magi-texture-light'}`} />
      
    </GlobalContext.Provider>
  );
}

export const useGlobal = () => {
  const context = useContext(GlobalContext);
  if (!context) throw new Error("useGlobal must be used within GlobalProvider");
  return context;
};