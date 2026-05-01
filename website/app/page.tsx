"use client";

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import { Search, Book, Layers, User, Calendar, Folder, FileText, ChevronRight, ChevronDown, Sun, Moon, BookOpen, Leaf } from 'lucide-react';
import { useGlobal } from '@/app/providers';
import { SPEAKER_COLOR_MAP } from '@/app/config/dictionary';
import { Story } from '@/components/Sidebar';
import AboutModal from '@/components/AboutModal';

type SearchEntry = {
  id: string;
  c: string; // content
  l: 'cn' | 'jp'; // lang
  _p?: string; // 预计算：剥离了说话人的纯对话文本（带空格，用于生成完美摘要）
  _n?: string; // 预计算：剥离了说话人且无空白的文本（用于极速匹配）
};

type StoryGroup = {
  folderName: string;
  items: Story[];
  totalCn: number;
  matchSnippets?: Record<string, string>; 
};

const CATEGORY_CONFIG: Record<string, { label: string; icon: any }> = {
  "main_story": { label: "主线", icon: Book },
  "event_story": { label: "活动", icon: Calendar },
  "character_story": { label: "角色", icon: User },
  "costume_story": { label: "服装", icon: Layers },
  "login_story": { label: "登录", icon: FileText },
  "mirror_story": { label: "镜层", icon: Folder },
  "scene0_main": { label: "S0主线", icon: Book },
  "scene0_sub": { label: "S0支线", icon: User },
  "Unclassified": { label: "其他", icon: Folder },
};

const getDisplayLabel = (story: Story) => {
  // 优先使用 titles.json 里的中文标题，其次 filename，最后 ID
  const label = story.title || story.filename_cn || story.filename_jp || story.id;
  return label.replace(/(_cn|_jp)?\.txt$/i, '');
};

// FolderCard 组件
const FolderCard = ({ group, theme }: { group: StoryGroup, theme: string }) => {
  const hasSearchMatches = group.matchSnippets && Object.keys(group.matchSnippets).length > 0;
  const [isOpen, setIsOpen] = useState(hasSearchMatches); 
  
  useEffect(() => {
    if (hasSearchMatches) setIsOpen(true);
  }, [hasSearchMatches]);

  const avgPercent = Math.round(group.items.reduce((sum, s) => sum + ((s as any).percent || (s.has_cn ? 100 : 0)), 0) / group.items.length);

  const isDark = theme === 'dark';
  let headerClass = "";
  let progressClass = "";

  if (isDark) {
    if (avgPercent === 0) headerClass = "bg-gray-800 border-gray-700 text-gray-400";
    else headerClass = `bg-emerald-900/40 border-emerald-800 text-emerald-100`;
    progressClass = "text-emerald-400";
  } else {
    if (avgPercent === 0) headerClass = "bg-black/5 border-black/10 text-black/50";
    else if (avgPercent === 100) headerClass = "bg-emerald-600 border-emerald-700 text-white";
    else headerClass = "bg-emerald-100 border-emerald-300 text-emerald-900";
    progressClass = avgPercent === 100 ? "text-emerald-100" : "text-emerald-700";
  }

  const displayTitle = group.folderName.replace(/^\d+ - /, '').replace(/^Event_\d+/, 'Event');
  const folderId = group.folderName.match(/^(\d+)/)?.[1] || "";

  return (
    <div className={`break-inside-avoid mb-3 rounded-lg border shadow-sm transition-all ${isDark ? 'border-gray-700' : 'border-black/10'}`}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full flex items-start justify-between px-3 py-3 text-left transition-colors border-b ${isOpen ? 'border-inherit' : 'border-transparent'} ${headerClass}`}
      >
        <div className="flex items-start gap-2 overflow-hidden w-full">
          <div className="mt-0.5 flex-shrink-0">
            {isOpen ? <ChevronDown size={16}/> : <ChevronRight size={16}/>}
          </div>
          {folderId && <span className="font-mono text-xs opacity-70 bg-black/10 px-1 rounded flex-shrink-0 mt-0.5">{folderId}</span>}
          <span 
            className="font-bold text-sm whitespace-normal break-words leading-tight flex-1 mr-2"
            style={{ color: SPEAKER_COLOR_MAP[displayTitle] || '' }}
          >
            {displayTitle}
          </span>
        </div>
        <span className={`text-[10px] font-mono mt-0.5 flex-shrink-0 ${progressClass}`}>{avgPercent}%</span>
      </button>

      {isOpen && (
        <div className={`p-2 ${isDark ? 'bg-gray-900' : 'bg-white/50'}`}>
          {/* 布局修复：使用 flex-wrap 替代 flex-col，横向排列 */}
          <div className="flex flex-wrap gap-2">
             {group.items.sort((a,b) => a.id.localeCompare(b.id)).map(story => {
               const label = getDisplayLabel(story);
               const p = (story as any).percent || 0;
               const snippet = group.matchSnippets?.[story.id];
               
               let btnClass = "";
               if (isDark) {
                  btnClass = p > 0 ? 'bg-emerald-900/30 border-emerald-700 text-emerald-400' : 'bg-gray-800 border-gray-700 text-gray-500';
               } else {
                  btnClass = p > 0 ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-white border-gray-200 text-gray-400';
               }

               return (
                 <Link 
                   key={story.id}
                   href={`/reader/${story.id}?cn=${encodeURIComponent(story.path_cn || '')}&jp=${encodeURIComponent(story.path_jp || '')}`}
                   // 如果有搜索结果，强制占满一行显示上下文；否则自适应宽度
                   className={`rounded border transition-all hover:scale-[1.01] ${btnClass} overflow-hidden ${snippet ? 'w-full' : ''}`}
                 >
                   <div className="px-2 py-1.5 flex justify-between items-center gap-2">
                      <span className="font-mono text-xs font-bold break-all">#{label}</span>
                      {p < 100 && p > 0 && <span className="text-[10px] opacity-60">{p}%</span>}
                   </div>
                   
                   {snippet && (
                     <div className={`px-2 py-1.5 text-xs font-serif border-t ${isDark ? 'border-white/10 text-gray-300' : 'border-black/5 text-gray-600'}`}>
                        ...{snippet}...
                     </div>
                   )}
                 </Link>
               );
             })}
          </div>
        </div>
      )}
    </div>
  );
};

export default function Home() {
  const [stories, setStories] = useState<Story[]>([]);
  const [searchIndex, setSearchIndex] = useState<SearchEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const[aboutOpen, setAboutOpen] = useState(false);
  // 新增：是否搜索日文文本
  const [searchJp, setSearchJp] = useState(false);
  
  const { theme, setTheme, lastCategory, setLastCategory } = useGlobal();
  const [searchMode, setSearchMode] = useState<'all' | 'title' | 'content'>('all');

// app/page.tsx 的 useEffect 部分
useEffect(() => {
  fetch('/story_index.json')
    .then(res => {
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      return res.json();
    })
    .then(data => {
        setStories(data);
        setLoading(false);
    })
    .catch(e => {
      console.error("Fetch error:", e);
      // 防止一直 loading
      setLoading(false); 
    });
}, []);

useEffect(() => {
    // 只要有搜索词且模式涉及内容，就去加载索引
    if (searchTerm.length > 0 && searchIndex.length === 0 && !searchLoading && (searchMode === 'all' || searchMode === 'content')) {
      setSearchLoading(true);
      
      // 智能加载逻辑：
      // 如果是在本地开发环境 (localhost)，尝试加载本地文件（如果存在）
      // 否则加载 R2 上的远程文件
      const SEARCH_INDEX_URL = process.env.NODE_ENV === 'development' 
        ? '/search_content.json' 
        : 'https://github.com/HiiragiNemu/magi-reader/releases/download/latest/search_content.json';

      fetch(SEARCH_INDEX_URL)
       .then(res => res.json())
       .then(data => {
        setSearchIndex(data.map((e: any) => {
          // 1. 核心修复：先消灭字面量的 "\n" 字符串，再消灭真正的换行和 @
          let cleanRaw = e.c
            .replace(/\\n/g, ' ')      // 处理字面量 \n
            .replace(/[@\n\r]/g, ' '); // 处理真实换行

          // 2. 剥离说话人前缀
          let pureText = cleanRaw.replace(/(^|\s)[^:：\s]+[:：]\s*/g, ' ');

          return {
            ...e,
            _p: pureText, 
            // 3. 核心优化：匹配索引 (_n) 删掉所有非文字内容（标点、空格、特殊符号）
            // 这样无论数据里有多少逗号或 \n，搜索时都不受影响
            _n: pureText.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, '').toLowerCase() 
          };
        }));
      })
        .catch(err => console.error("搜索索引加载失败:", err))
        .finally(() => setSearchLoading(false));
    }
  }, [searchTerm, searchMode]);

  const { categories, displayedGroups } = useMemo(() => {
    const cats = new Set<string>();
    const groups: Record<string, StoryGroup> = {};
    const lowerSearch = searchTerm.toLowerCase().trim();

    // 1. 预处理全文搜索匹配 (仅当模式为 all 或 content 时)
    const textMatches: Record<string, string> = {}; 
    const enableContentSearch = (searchMode === 'all' || searchMode === 'content') && lowerSearch && searchIndex.length > 0;
    
if (enableContentSearch) {
      // 搜索词也删掉所有标点符号和空格
      const searchFlat = lowerSearch.replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, '');
      
      if (searchFlat) {
        searchIndex.forEach(entry => {
          const flatContent = entry._n || '';
          const idx = flatContent.indexOf(searchFlat);
          
          if (idx !== -1 && entry._p) {
            // 摘要定位：依然基于去标点后的位置映射
            let origIdx = 0, flatCount = 0;
            // 这里的判定逻辑也需要同步改为“非文字内容跳过”
            while (flatCount < idx && origIdx < entry._p.length) {
              if (/[\u4e00-\u9fa5a-zA-Z0-9]/.test(entry._p[origIdx])) flatCount++;
              origIdx++;
            }
            
            const start = Math.max(0, origIdx - 15);
            const end = Math.min(entry._p.length, origIdx + searchFlat.length + 30);
            textMatches[entry.id] = "..." + entry._p.substring(start, end).trim() + "...";
          }
        });
      }
    }

    // 2. 遍历所有故事进行过滤
    stories.forEach(s => {
      const cat = s.category || "Unclassified";
      cats.add(cat);
      
      // 匹配条件
      const idMatch = s.id.toLowerCase().includes(lowerSearch);
      
      // 文件夹名匹配 (去除 ID 前缀后)
      const cleanFolder = s.folder.replace(/^\d+ - /, '').toLowerCase();
      const folderMatch = cleanFolder.includes(lowerSearch);
      
      // 文件名匹配
      const fileMatch = (s.filename_cn || "").toLowerCase().includes(lowerSearch);
      
      // 内容匹配
      const contentMatch = !!textMatches[s.id];

      let isMatch = false;

      if (!lowerSearch) {
        isMatch = true; // 无搜索词，全显
      } else {
        if (searchMode === 'title') {
          // 仅搜 ID、标题、文件名
          isMatch = idMatch || folderMatch || fileMatch;
        } else if (searchMode === 'content') {
          // 仅搜内容
          isMatch = contentMatch;
        } else {
          // 全部 (all)
          isMatch = idMatch || folderMatch || fileMatch || contentMatch;
        }
      }

      // 如果有搜索词 -> 显示所有匹配项 (忽略分类)
      // 如果无搜索词 -> 只显示当前选中的分类 (activeCategory)
      const shouldShow = lowerSearch ? isMatch : (cat === lastCategory);

      if (shouldShow) {
        const key = s.folder;
        if (!groups[key]) groups[key] = { folderName: key, items: [], totalCn: 0, matchSnippets: {} };
        groups[key].items.push(s);
        if (s.has_cn) groups[key].totalCn++;
        
        // 注入搜索摘要
        if (contentMatch && groups[key].matchSnippets) {
           groups[key].matchSnippets![s.id] = textMatches[s.id];
        }
      }
    });

    const sortedGroups = Object.values(groups).sort((a, b) => {
      const idA = a.folderName.match(/^(\d+)/)?.[1] || "";
      const idB = b.folderName.match(/^(\d+)/)?.[1] || "";
      return idA.localeCompare(idB) || a.folderName.localeCompare(b.folderName);
    });

    return { categories: Array.from(cats).sort(), displayedGroups: sortedGroups };
  }, [stories, lastCategory, searchTerm, searchIndex, searchMode]); // 依赖项必须包含 searchMode

  const CategoryNav = ({ mobile = false }) => (
    <nav className={mobile ? "flex overflow-x-auto p-2 gap-2 no-scrollbar bg-inherit border-b border-black/5" : "flex-1 overflow-y-auto p-2 space-y-1"}>
      {categories.map(cat => {
        const config = CATEGORY_CONFIG[cat] || { label: cat, icon: Folder };
        const Icon = config.icon;
        const isActive = lastCategory === cat && !searchTerm;
        
        const activeClass = theme === 'dark' ? 'bg-emerald-900/50 text-emerald-400 border-emerald-500' : 'bg-emerald-50 text-emerald-700 border-emerald-500';
        const inactiveClass = "text-gray-500 hover:bg-black/5 border-transparent";
        
        return (
          <button
            key={cat}
            onClick={() => { setLastCategory(cat); setSearchTerm(''); }}
            className={`
              flex items-center gap-2 px-3 py-2 rounded-md text-sm font-bold transition-all whitespace-nowrap
              ${mobile ? 'border-b-2 rounded-none' : 'border-l-4'}
              ${isActive ? activeClass : inactiveClass}
            `}
          >
            <Icon size={16} />
            <span>{config.label}</span>
          </button>
        );
      })}
    </nav>
  );

  if (loading) return <div className="flex h-screen items-center justify-center opacity-50">数据加载中...</div>;

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className={`hidden md:flex w-64 border-r flex-col z-20 flex-shrink-0 ${theme === 'dark' ? 'border-gray-800 bg-gray-900' : 'border-black/5 bg-inherit'}`}>
        <div className="p-5 border-b border-inherit">
          <h1 className="text-xl font-black bg-clip-text text-transparent bg-gradient-to-r from-emerald-600 to-teal-500">MagiReader</h1>
          <p className="text-xs opacity-50 mt-1">Archive v3.0</p>
        </div>
        <CategoryNav />
      </aside>

      <main className="flex-1 flex flex-col min-w-0 bg-transparent">
        <header className={`border-b p-3 backdrop-blur z-10 flex flex-col gap-3 ${theme === 'dark' ? 'border-gray-800 bg-gray-900/90' : 'border-black/5 bg-white/60'}`}>
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-lg flex gap-2">
              <div className="relative flex-1">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none opacity-50"><Search size={16} /></div>
                <input
                  type="text"
                  placeholder={searchLoading ? "正在下载索引..." : "搜索..."}
                  className={`block w-full pl-9 pr-3 py-2 border rounded-lg text-sm outline-none transition-all ${theme==='dark'?'bg-gray-800 border-gray-700':'bg-white/50 border-black/10'}`}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              {/* === 插入开始：搜索范围切换 === */}
                 <div className="flex items-center bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5 border border-gray-200 dark:border-gray-700 shrink-0">
                   {[
                     { id: 'all', label: '全部' },
                     { id: 'title', label: '标题' },
                     { id: 'content', label: '正文' }
                   ].map((opt) => (
                     <button
                       key={opt.id}
                       onClick={() => setSearchMode(opt.id as any)}
                       className={`
                         px-2 py-1.5 text-xs font-bold rounded-md transition-all
                         ${searchMode === opt.id
                           ? 'bg-white dark:bg-gray-600 text-blue-600 dark:text-blue-300 shadow-sm'
                           : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'}
                       `}
                     >
                       {opt.label}
                     </button>
                   ))}
                 </div>
                 {/* === 插入结束 === */}
              
              {/* 日文搜索开关 */}
              <label className={`flex items-center gap-1 px-2 rounded cursor-pointer border ${searchJp ? (theme==='dark'?'bg-blue-900/30 border-blue-800 text-blue-400':'bg-blue-50 border-blue-200 text-blue-700') : 'border-transparent opacity-60'}`}>
                <input type="checkbox" checked={searchJp} onChange={e => setSearchJp(e.target.checked)} className="accent-blue-500 w-3 h-3" />
                <span className="text-xs font-bold whitespace-nowrap">JP</span>
              </label>
              <button onClick={() => setAboutOpen(true)} className={`px-2.5 py-1 rounded cursor-pointer border text-xs font-bold whitespace-nowrap transition-all ${theme==='dark' ? 'bg-emerald-900/30 border-emerald-800 text-emerald-400 hover:bg-emerald-800' : 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'}`}>关于我们</button>
            </div>
            
            <div className={`flex gap-1 p-1 rounded-full self-end md:self-auto ${theme==='dark'?'bg-black/20':'bg-black/5'}`}>
              {[
                {k:'light',i:Sun}, {k:'paper',i:BookOpen}, {k:'green',i:Leaf}, {k:'dark',i:Moon}
              ].map(o => (
                <button key={o.k} onClick={()=>setTheme(o.k as any)} className={`p-2 rounded-full ${theme===o.k ? 'bg-white shadow text-black' : 'opacity-40'}`}>
                  <o.i size={14}/>
                </button>
              ))}
            </div>
          </div>

          <div className="md:hidden -mx-3">
             <CategoryNav mobile={true} />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-3 md:p-6 scroll-smooth">
          <div className="max-w-7xl mx-auto">
            {!searchTerm && <h2 className="text-xl font-bold mb-4 opacity-80 px-1">{CATEGORY_CONFIG[lastCategory]?.label}</h2>}
            {searchTerm && <h2 className="text-xl font-bold mb-4 opacity-80 px-1">搜索结果: "{searchTerm}" {searchJp ? '(含日文)' : ''}</h2>}
            
            <div className="columns-1 md:columns-2 xl:columns-3 gap-4 space-y-4">
              {displayedGroups.map(group => (
                <FolderCard key={group.folderName} group={group} theme={theme} />
              ))}
            </div>
            {displayedGroups.length === 0 && (
                <div className="text-center opacity-50 mt-10">没有找到相关剧情</div>
            )}
             <div className="h-20"></div>
          </div>
        </div>
      </main>
      <AboutModal isOpen={aboutOpen} onClose={() => setAboutOpen(false)} theme={theme} />
    </div>
  );
}