"use client";

import { useState, useMemo, useEffect } from 'react';
import Link from 'next/link';
import { Folder, ChevronRight, ChevronDown, Book, User, Calendar, Layers, FileText, X } from 'lucide-react';
import { useGlobal } from '@/app/providers';
import { SPEAKER_COLOR_MAP } from '@/app/config/dictionary';
export type Story = {
  id: string;
  category: string;
  folder: string;
  percent: number;
  has_cn: boolean;
  filename_cn?: string;
  filename_jp?: string;
  path_cn?: string;
  path_jp?: string;
};

export const CATEGORY_CONFIG: Record<string, { label: string; icon: any }> = {
  "main_story": { label: "主线剧情", icon: Book },
  "event_story": { label: "活动剧情", icon: Calendar },
  "character_story": { label: "魔法少女", icon: User },
  "costume_story": { label: "服装剧情", icon: Layers },
  "login_story": { label: "登录剧情", icon: FileText },
  "mirror_story": { label: "镜层/其他", icon: Folder },
  "scene0_main": { label: "Scene0 主线", icon: Book },
  "scene0_sub": { label: "Scene0 支线", icon: User },
  "Unclassified": { label: "未分类", icon: Folder },
};

type SidebarProps = {
  stories: Story[];
  currentId?: string;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
};

// 辅助：绝对不缩减名字，只去后缀
const getDisplayLabel = (story: Story) => {
  // 优先中文名，其次日文名
  const name = story.filename_cn || story.filename_jp || story.id;
  // 只移除 .txt 后缀 (不移除 _cn / _jp 因为这是内部后缀，脚本里生成的)
  // 如果脚本生成的是 xxx_cn.txt，我们要展示 xxx
  return name.replace(/(_cn|_jp)?\.txt$/i, '');
};

export default function Sidebar({ stories, currentId, isOpen, onClose, className }: SidebarProps) {
  const { theme, lastCategory, setLastCategory } = useGlobal();
  const [expandedCats, setExpandedCats] = useState<Record<string, boolean>>({});
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});

// 容器样式 - 增加 backdrop-blur 和 bg-opacity
const themeClass = theme === 'dark' ? 'bg-gray-900/70 glass-morphism border-gray-700 text-gray-300' : 
                     theme === 'paper' ? 'bg-[#f0e6d2]/60 glass-morphism border-[#dcd6b6] text-[#5c4b37]' : 
                     theme === 'green' ? 'bg-[#d8e6d1]/60 glass-morphism border-[#b8cbb0] text-[#1b4d1b]' :
                     'bg-white/70 glass-morphism border-gray-200 text-gray-600';

  const groupedData = useMemo(() => {
    const data: Record<string, Record<string, Story[]>> = {};
    stories.forEach(s => {
      const cat = s.category || "Unclassified";
      const folder = s.folder;
      if (!data[cat]) data[cat] = {};
      if (!data[cat][folder]) data[cat][folder] = [];
      data[cat][folder].push(s);
    });
    return data;
  }, [stories]);

  const handleCatClick = (cat: string) => {
    setLastCategory(cat);
    setExpandedCats(p => ({ ...p, [cat]: !p[cat] }));
  };

  const toggleFolder = (folder: string) => setExpandedFolders(p => ({ ...p, [folder]: !p[folder] }));

  useEffect(() => {
    if (currentId && stories.length > 0) {
      const target = stories.find(s => s.id === currentId);
      if (target) {
        setExpandedCats(prev => ({ ...prev, [target.category]: true }));
        setExpandedFolders(prev => ({ ...prev, [target.folder]: true }));
        setTimeout(() => {
          document.getElementById(`nav-item-${currentId}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }, 100);
      }
    }
  }, [currentId, stories]);

  useEffect(() => {
  if (isOpen && currentId) {
    setTimeout(() => {
      document.getElementById(`nav-item-${currentId}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 200); // 增加延迟以确保移动端 sidebar 动画完成后滚动
  }
}, [isOpen, currentId]);
  // 基础样式
  const containerClass = `
    flex flex-col border-r overflow-hidden transition-transform duration-300 z-50
    fixed inset-y-0 left-0 w-72 md:relative md:transform-none
    ${isOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full md:translate-x-0'}
    ${themeClass} ${className}
  `;

  // 悬停样式
  const hoverClass = theme === 'green' ? 'hover:bg-[#b0e2bd]' : theme === 'dark' ? 'hover:bg-gray-800' : 'hover:bg-black/5';

  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black/60 z-40 md:hidden backdrop-blur-sm" onClick={onClose} />}
      <aside className={containerClass}>
        <div className="p-4 border-b flex justify-between items-center bg-inherit shrink-0">
          <Link href="/" className="font-black text-xl bg-clip-text text-transparent bg-gradient-to-r from-emerald-600 to-teal-500">
             MagiReader
          </Link>
          <button 
            onClick={onClose} 
            className={`md:hidden p-2 rounded-full hover:bg-black/10 active:scale-95 ${theme === 'dark' ? 'text-white' : 'text-gray-800'}`}
          >
            <X size={24}/>
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
          {Object.keys(groupedData).sort().map(cat => {
            const config = CATEGORY_CONFIG[cat] || { label: cat, icon: Folder };
            const Icon = config.icon;
            const isCatOpen = expandedCats[cat];

            return (
              <div key={cat} className="mb-1">
                <button 
                  onClick={() => handleCatClick(cat)}
                  className={`w-full flex items-center gap-2 px-2 py-3 rounded-md text-sm font-bold transition-colors ${isCatOpen ? 'bg-black/10' : 'opacity-70'} ${hoverClass}`}
                >
                  <span className="shrink-0">{isCatOpen ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}</span>
                  <Icon size={18} className="shrink-0" />
                  <span className="whitespace-nowrap">{config.label}</span>
                </button>

                {isCatOpen && (
                  <div className="ml-2 pl-2 border-l-2 border-current border-opacity-10 mt-1 space-y-1">
                    {Object.keys(groupedData[cat]).sort().map(folderName => {
                      const isFolderOpen = expandedFolders[folderName];
                      const items = groupedData[cat][folderName].sort((a,b) => a.id.localeCompare(b.id));
                      
                      // 文件夹整体进度计算 (用于颜色)
                      const avgPercent = Math.round(items.reduce((sum, s) => sum + (s.percent || 0), 0) / items.length);
                      
                      // 文件夹标题颜色 (模仿主页 FolderCard Header)
                      let folderColorClass = "";
                      if (theme === 'dark') {
                          if (avgPercent === 100) folderColorClass = "text-emerald-400";
                          else if (avgPercent > 0) folderColorClass = "text-emerald-600";
                          else folderColorClass = "text-gray-500";
                      } else {
                          if (avgPercent === 100) folderColorClass = "text-emerald-700 font-bold";
                          else if (avgPercent > 0) folderColorClass = "text-emerald-600";
                          else folderColorClass = "text-gray-500";
                      }

// 🟢 修改开始：针对角色和服装，保留原始文件夹名（带编号）；其他分类保持简化
let folderDisplay = folderName;
// 如果是 角色(character_story) 或 服装(costume_story)，直接显示文件夹原名 (如 "1001 - 环彩羽")
if (cat === 'character_story' || cat === 'costume_story') {
  folderDisplay = folderName; 
} else {
  // 其他分类（如主线），去掉前面的数字前缀，保持简洁
  folderDisplay = folderName.replace(/^\d+ - /, '').replace(/^Event_\d+/, 'Event');
}
// 🔴 修改结束
                      return (
                        <div key={folderName}>
                          <button 
                            onClick={() => toggleFolder(folderName)}
                            className={`w-full flex items-center justify-between text-left px-2 py-2 rounded text-xs transition-colors ${hoverClass}`}
                          >
                          <span 
                            className={`whitespace-normal break-words leading-tight mr-1 ${folderColorClass}`}
                            style={{ color: SPEAKER_COLOR_MAP[folderDisplay] || '' }}
                          >
                            {folderDisplay}
                          </span>                            <span className="text-[10px] opacity-50 bg-black/5 px-1 rounded shrink-0">{items.length}</span>
                          </button>

                          {isFolderOpen && (
                            <div className="ml-2 space-y-0.5 mt-0.5">
                              {items.map(story => {
                                 const label = getDisplayLabel(story);
                                 const isActive = story.id === currentId;
                                 const p = story.percent || (story.has_cn ? 100 : 0);
                                 
                                 // === 颜色逻辑：照抄主页 ===
                                 let btnClass = "";
                                 
                                 // Active 状态优先
                                 if (isActive) {
                                     btnClass = theme === 'green' ? 'bg-[#2E7D32] text-white' : 'bg-blue-600 text-white shadow-md';
                                 } else {
                                     // 未选中状态：根据进度显示颜色
                                     if (theme === 'dark') {
                                         if (p === 100) btnClass = "bg-emerald-900/40 text-emerald-300 border border-emerald-800";
                                         else if (p > 0) btnClass = "bg-emerald-900/20 text-emerald-500 border border-emerald-900";
                                         else btnClass = "bg-transparent text-gray-500 hover:bg-gray-800";
                                     } else {
                                         if (p === 100) btnClass = "bg-emerald-100 text-emerald-900 border border-emerald-200";
                                         else if (p > 0) btnClass = "bg-emerald-50 text-emerald-800 border border-emerald-100";
                                         else btnClass = "bg-transparent text-gray-400 hover:bg-gray-100";
                                     }
                                 }

                                 return (
                                   <Link
                                     key={story.id}
                                     id={`nav-item-${story.id}`}
                                     href={`/reader/${story.id}?cn=${encodeURIComponent(story.path_cn||'')}&jp=${encodeURIComponent(story.path_jp||'')}`}
                                     onClick={onClose}
                                     className={`
  block px-2 py-1.5 rounded-sm text-xs font-mono transition-all truncate border-l-2
  ${isActive 
    ? (theme === 'green' ? 'bg-[#2E7D32] text-white border-[#1B5E20]' : theme === 'dark' ? 'bg-blue-900/30 text-blue-300 border-blue-500' : 'bg-blue-50 text-blue-700 border-blue-500')
    : (p > 0
        ? (theme === 'dark' ? 'bg-emerald-900/30 text-emerald-400 border-emerald-500/50 hover:bg-emerald-900/40' : 'bg-emerald-50 text-emerald-700 border-emerald-500/50 hover:bg-emerald-100')
        : (theme === 'dark' ? 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700' : 'bg-white text-gray-400 border-gray-200 hover:bg-gray-50')
      )
  }
`}
                                     title={label} // 悬停显示完整名
                                   >
                                     <span className="mr-2">#{label}</span>
                                     {p < 100 && !isActive && <span className="text-[9px] opacity-60 scale-90 inline-block">{p}%</span>}
                                   </Link>
                                 );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </aside>
    </>
  );
}