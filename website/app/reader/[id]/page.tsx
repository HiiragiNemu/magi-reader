"use client";

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Menu, Settings, Download, ArrowLeft, Sun, Moon, BookOpen, Leaf, X, Search } from 'lucide-react';
import Sidebar, { Story } from '@/components/Sidebar';
import { useGlobal } from '@/app/providers';
import { SPEAKER_COLOR_MAP, NAME_TRANSLATE_MAP } from '@/app/config/dictionary';
type StoryLine = {
  speaker: string;
  text: string;
  isHeader?: boolean;
};

const parseText = (raw: string): StoryLine[] => {
  if (!raw) return [];
  const lines = raw.split('\n');
  const result: StoryLine[] = [];
  let currentSpeaker = '';
  let currentText: string[] = [];

  const flush = () => {
    if (currentSpeaker || currentText.length > 0) {
      result.push({ speaker: currentSpeaker, text: currentText.join('\n') });
      currentSpeaker = '';
      currentText = [];
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith('---') && trimmed.includes('[Section')) {
      flush();
      result.push({ speaker: '', text: trimmed, isHeader: true });
      continue;
    }
    const colonIdx = trimmed.indexOf(':');
    if (colonIdx > -1 && colonIdx < 20) {
      flush();
      currentSpeaker = trimmed.substring(0, colonIdx).trim();
      currentText.push(trimmed.substring(colonIdx + 1).trim().replace(/\\n/g, '\n'));
    } else {
      currentText.push(trimmed.replace(/\\n/g, '\n'));
    }
  }
  flush();
  return result;
};

export default function ReaderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const cnPath = searchParams.get('cn') || '';
  const jpPath = searchParams.get('jp') || '';

  const { theme, setTheme } = useGlobal();
  const [cnLines, setCnLines] = useState<StoryLine[]>([]);
  const [jpLines, setJpLines] = useState<StoryLine[]>([]);
  const [loading, setLoading] = useState(true);
  
  // 默认模式：如果都有则 split，否则 cn/jp
  const [mode, setMode] = useState<'cn' | 'split' | 'jp'>('cn');
  
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  
  // 默认字号更小，行高更紧
  const [fontSize, setFontSize] = useState(15); 
  const [lineHeight, setLineHeight] = useState(1.1);
  
  const [allStories, setAllStories] = useState<Story[]>([]);
  // --- 汉化协助系统 ---
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedCnLines, setEditedCnLines] = useState<StoryLine[]>([]);

  // 1. 克隆并替换名字
// A. 仅翻译名字（内容留空，方便纯手打）
  const initEmptyWithNames = () => {
    if (!jpLines || jpLines.length === 0) return;
    const empty = jpLines.map(line => ({
      ...line,
      speaker: NAME_TRANSLATE_MAP[line.speaker] || line.speaker,
      text: "" // 内容清空
    }));
    setEditedCnLines(empty);
    setMode('split');
  };

  // B. 克隆日文 + 翻译名字（作为对照或机翻基底）
  const initWithJpContent = () => {
    if (!jpLines || jpLines.length === 0) return;
    const cloned = jpLines.map(line => ({
      ...line,
      speaker: NAME_TRANSLATE_MAP[line.speaker] || line.speaker,
      text: line.text // 保留日文原文
    }));
    setEditedCnLines(cloned);
    setMode('split');
  };

  // 2. 导出下载
  const downloadTxt = () => {
    const linesToExport = editedCnLines.length > 0 ? editedCnLines : cnLines;
    const content = linesToExport.map(l => 
      l.isHeader ? l.text : `${l.speaker}: ${l.text}`
    ).join('\n');
    const blob = new Blob(["\ufeff" + content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${id}_translated.txt`; a.click();
  };

  // 3. 上传本地 TXT
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      setEditedCnLines(parseText(text));
    };
    reader.readAsText(file);
  };

  // 4. 提交到 Cloudflare D1
  const submitToCloud = async () => {
    if (editedCnLines.length === 0) return alert("内容为空，无法提交");
    
    // 生成纯文本格式
    const contentText = editedCnLines.map(l => 
      l.isHeader ? l.text : `${l.speaker}: ${l.text}`
    ).join('\n');

    try {
      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          story_id: id,
          content: contentText,
          author: 'Anonymous', // 后续可以加登录功能
        })
      });
      
      if (res.ok) alert("提交成功！感谢您的贡献，管理员审核后将更新。");
      else alert("提交失败，请稍后再试。");
    } catch (e) {
      alert("网络错误");
    }
  };
  
  const currentStory = allStories.find(s => s.id === id);

  // --- 新增/修改搜索相关 State ---
  const [searchQuery, setSearchQuery] = useState('');
  const [currentMatchIdx, setCurrentMatchIdx] = useState(-1);
  const [matchedIndices, setMatchedIndices] = useState<number[]>([]);

  useEffect(() => {
    fetch('/story_index.json').then(r => r.json()).then(setAllStories);
    async function load() {
      try {
        const [cnT, jpT] = await Promise.all([
          cnPath ? fetch(cnPath).then(r => r.ok ? r.text() : '') : '',
          jpPath ? fetch(jpPath).then(r => r.ok ? r.text() : '') : ''
        ]);
        const pCn = parseText(cnT);
        const pJp = parseText(jpT);
        setCnLines(pCn);
        setJpLines(pJp);
        
        // 自动判定模式
        if (pCn.length > 0 && pJp.length > 0) setMode('split');
        else if (pCn.length === 0) setMode('jp');
        else setMode('cn');
        
      } finally { setLoading(false); }
    }
    load();
  }, [cnPath, jpPath]);

  // 样式表
  const themeStyles = {
    light: "bg-white text-gray-900",
    dark: "bg-[#0f172a] text-gray-200",
    paper: "bg-[#f0e6d2] text-[#4a4036]",
    green: "bg-[#C7EDCC] text-[#003300]",
  };
  const headerStyles = {
    light: "border-gray-200 bg-white",
    dark: "border-gray-800 bg-[#0f172a]",
    paper: "border-[#e6dfc5] bg-[#f0e6d2]",
    green: "border-[#A8D8B9] bg-[#C7EDCC]",
  };
  const speakerColor = {
    light: "text-blue-700 bg-blue-50",
    dark: "text-blue-300 bg-blue-900/30",
    paper: "text-[#8c5e2d] bg-[#e6d8b8]",
    green: "text-green-800 bg-green-100",
  };

  const alignSections = (cn: StoryLine[], jp: StoryLine[]) => {
    const result: { cn?: StoryLine; jp?: StoryLine }[] = [];
    
    let i = 0, j = 0;
    
    while (i < cn.length || j < jp.length) {
      const c = cn[i];
      const p = jp[j];
  
      if (c?.isHeader && p?.isHeader) {
        const cNum = c.text.match(/Section (\d+)/)?.[1];
        const pNum = p.text.match(/Section (\d+)/)?.[1];
        
        if (cNum === pNum) {
          result.push({ cn: c, jp: p });
          i++; j++;
        } else if ((cNum || 0) < (pNum || 0)) {
          result.push({ cn: c, jp: undefined });
          i++;
        } else {
          result.push({ cn: undefined, jp: p });
          j++;
        }
        continue;
      }
  
      if (c?.isHeader) {
        result.push({ cn: c, jp: undefined });
        i++;
        continue;
      }
      if (p?.isHeader) {
        result.push({ cn: undefined, jp: p });
        j++;
        continue;
      }
  
      result.push({ cn: c, jp: p });
      if (c) i++;
      if (p) j++;
    }
    
    return result;
  };
  
  const renderList = alignSections(cnLines, jpLines);

  // 当搜索词变化时，计算所有匹配行
  useEffect(() => {
    if (!searchQuery) {
      setMatchedIndices([]);
      setCurrentMatchIdx(-1);
      return;
    }
    const lowerQuery = searchQuery.toLowerCase();
    const indices: number[] = [];
    
    renderList.forEach((row, idx) => {
      const cnText = row.cn?.text?.toLowerCase() || '';
      const cnSpeaker = row.cn?.speaker?.toLowerCase() || '';
      const jpText = row.jp?.text?.toLowerCase() || '';
      const jpSpeaker = row.jp?.speaker?.toLowerCase() || '';

      if (cnText.includes(lowerQuery) || cnSpeaker.includes(lowerQuery) || 
          jpText.includes(lowerQuery) || jpSpeaker.includes(lowerQuery)) {
        indices.push(idx);
      }
    });
    
    setMatchedIndices(indices);
    setCurrentMatchIdx(indices.length > 0 ? 0 : -1);
    
    if (indices.length > 0) {
       setTimeout(() => {
         document.getElementById(`line-${indices[0]}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
       }, 100);
    }
  }, [searchQuery, renderList.length]);

  // 跳转到下一个匹配项
  const jumpToNextMatch = () => {
    if (matchedIndices.length === 0) return;
    const nextIdx = (currentMatchIdx + 1) % matchedIndices.length;
    setCurrentMatchIdx(nextIdx);
    document.getElementById(`line-${matchedIndices[nextIdx]}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  // 升级后的 renderStyledText，支持 forceHighlight（角色名搜索时整段高亮）
  // 增强版文本解析逻辑
  const renderStyledText = (text: string, forceHighlight: boolean = false) => {
    // 1. 处理 <red> 标签：将字符串切分为 [普通文本, <red>文本, 普通文本]
    const redParts = text.split(/(<red>.*?<\/red>)/g);
    
    return redParts.map((part, index) => {
      let isRedTag = false;
      let content = part;

      if (part.startsWith('<red>') && part.endsWith('</red>')) {
        content = part.replace(/<\/?red>/g, '');
        isRedTag = true;
      }

      // 2. 处理搜索高亮逻辑
      if (searchQuery && (content.toLowerCase().includes(searchQuery.toLowerCase()) || forceHighlight)) {
        const regex = new RegExp(`(${searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        const searchParts = content.split(regex);
        
        return (
          <span key={index} className={isRedTag ? "text-red-500 font-bold" : ""}>
            {searchParts.map((sp, i) => 
              regex.test(sp) 
                ? <span key={i} className="bg-red-100 text-red-700 outline outline-1 outline-red-500 rounded px-0.5 shadow-sm mx-0.5">{sp}</span> 
                : sp
            )}
          </span>
        );
      }

      // 3. 正常渲染（含红色标签处理）
      return (
        <span key={index} className={isRedTag ? "text-red-500 font-bold" : ""}>
          {content}
        </span>
      );
    });
  };

  if (loading) return <div className="flex h-screen items-center justify-center opacity-50">Loading...</div>;

  return (
    <div className={`flex h-screen overflow-hidden ${themeStyles[theme]}`}>
      
      <Sidebar 
        stories={allStories} 
        currentId={id} 
        isOpen={sidebarOpen} 
        onClose={()=>setSidebarOpen(false)} 
        className={sidebarOpen ? "" : "hidden md:flex"}
      />

      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* 顶部栏 */}
        <header className={`flex items-center justify-between px-4 py-2 border-b z-20 shrink-0 ${headerStyles[theme]}`}>
          <div className="flex items-center gap-3 overflow-hidden">
            <button onClick={() => setSidebarOpen(true)} className="md:hidden p-2 -ml-2 rounded hover:bg-black/5">
              <Menu size={20} />
            </button>
            <div className="flex flex-col min-w-0">
              <div className="text-[10px] opacity-50 flex gap-1 whitespace-nowrap">
                <span>{currentStory?.folder || "Loading..."}</span>
              </div>
              <div className="font-bold text-sm truncate flex items-center gap-2">
                <span className="font-mono text-emerald-600">{id}</span>
                {cnPath && (
                  <a href={cnPath} download className="flex items-center gap-1 opacity-50 hover:opacity-100 hover:text-green-600 border border-transparent hover:border-green-200 px-1 rounded transition-all">
                    <Download size={14}/>
                    <span className="text-[10px]">CN</span>
                  </a>
                )}
                {jpPath && (
                  <a href={jpPath} download className="flex items-center gap-1 opacity-50 hover:opacity-100 hover:text-blue-600 border border-transparent hover:border-blue-200 px-1 rounded transition-all">
                    <Download size={14}/>
                    <span className="text-[10px]">JP</span>
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* --- PC端常驻搜索栏 --- */}
          <div className="hidden md:flex flex-1 max-w-md mx-4 relative group">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search size={14} className="text-gray-400 group-focus-within:text-blue-500"/>
            </div>
            <input 
              type="text" 
              placeholder="页内搜索 (Enter跳转)" 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && jumpToNextMatch()}
              className={`w-full pl-9 pr-12 py-1.5 text-sm rounded-full border transition-all outline-none 
                ${theme === 'dark' 
                  ? 'bg-gray-800 border-gray-700 text-gray-200 focus:border-blue-500' 
                  : 'bg-gray-100 border-transparent focus:bg-white focus:border-blue-400 focus:ring-2 focus:ring-blue-100'
                }`}
            />
            {searchQuery && (
               <div className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 font-mono">
                 {matchedIndices.length > 0 ? `${currentMatchIdx + 1}/${matchedIndices.length}` : '0'}
               </div>
            )}
          </div>

          <div className="flex items-center gap-3 shrink-0">
                      {/* 协助汉化按钮 - 独立且增加移动端适配 */}
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setIsEditMode(!isEditMode);
                          // 修正逻辑：如果开启编辑且当前为空，根据渲染列表初始化对应长度的空行
                          if(!isEditMode && editedCnLines.length === 0) {
                            setEditedCnLines(cnLines.length > 0 ? [...cnLines] : renderList.map(r => ({ speaker: r.jp?.speaker || "", text: "" })));
                          }
                        }} 
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-all z-30 ${isEditMode ? 'bg-emerald-600 text-white shadow-lg' : 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'}`}
                      >
                        <Leaf size={14} />
                        <span className="hidden sm:inline">{isEditMode ? "返回阅读" : "协助汉化"}</span>
                      </button>

                      {/* 语言切换 */}
                      <div className={`flex rounded p-0.5 text-[10px] font-bold ${theme==='dark'?'bg-white/10':'bg-black/5'}`}>
                        {['cn','split','jp'].map(m => (
                          <button key={m} onClick={()=>setMode(m as any)} className={`px-2 py-1 rounded ${mode===m ? (theme==='dark'?'bg-gray-700 text-white':'bg-white shadow') : 'opacity-40'}`}>
                            {m==='cn'?'中':m==='jp'?'日':'双'}
                          </button>
                        ))}
                      </div>
                      
                      {/* 设置按钮 - 独立 */}
                      <button onClick={()=>setShowSettings(true)} className="p-2 rounded hover:bg-black/5 text-gray-500">
                        <Settings size={18}/>
                      </button>
                    </div>
        </header>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto scroll-smooth p-2 md:p-6" style={{ fontSize: `${fontSize}px`, lineHeight }}>
                    <div className="max-w-6xl mx-auto pb-20">
 {isEditMode && (
  <div className="mb-6 p-4 rounded-xl bg-emerald-50/80 border border-emerald-200 shadow-sm backdrop-blur-sm">
    <div className="flex flex-wrap gap-3 items-center">
      <span className="text-xs font-bold text-emerald-800 opacity-70 mr-2">初始化:</span>
      
      <button onClick={initEmptyWithNames} className="px-3 py-1.5 bg-white border border-emerald-300 text-emerald-700 rounded-lg text-xs font-bold hover:bg-emerald-50 active:scale-95 transition-all">
        1. 仅填入译名 (空文本)
      </button>
      
      <button onClick={initWithJpContent} className="px-3 py-1.5 bg-white border border-emerald-300 text-emerald-700 rounded-lg text-xs font-bold hover:bg-emerald-50 active:scale-95 transition-all">
        2. 填入日文原文
      </button>

      <div className="h-4 w-px bg-emerald-300 mx-1"></div>
      
      <label className="cursor-pointer px-3 py-1.5 bg-blue-50 border border-blue-200 text-blue-700 rounded-lg text-xs font-bold hover:bg-blue-100 transition-all flex items-center gap-1">
        <span>📂 上传本地 TXT</span>
        <input type="file" accept=".txt" className="hidden" onChange={handleFileUpload} />
      </label>

      <button onClick={downloadTxt} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-bold shadow hover:bg-blue-700 active:scale-95 transition-all ml-auto">
        📥 下载当前进度
      </button>
      
      <button onClick={submitToCloud} className="px-3 py-1.5 bg-purple-600 text-white rounded-lg text-xs font-bold shadow hover:bg-purple-700 active:scale-95 transition-all">
        🚀 提交审核
      </button>
    </div>
    <div className="mt-2 text-[10px] text-emerald-600/60 pl-1">
      * 提示：提交审核后，管理员通过后才会更新到网站。请优先下载 TXT 本地保存。
    </div>
  </div>
)}
            {/* --- 移动端搜索栏 (随页面滚动) --- */}
            <div className="md:hidden mb-4 px-1">
               <div className="relative">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
                  <input 
                    type="text" 
                    placeholder="搜索角色或对话..." 
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && jumpToNextMatch()}
                    className={`w-full pl-10 pr-4 py-2.5 rounded-lg border text-sm outline-none shadow-sm
                      ${theme === 'dark' 
                        ? 'bg-gray-800 border-gray-700 text-gray-100 placeholder-gray-600' 
                        : 'bg-white border-gray-200 text-gray-900 placeholder-gray-400'
                      }`}
                  />
                  {searchQuery && (
                     <button 
                       onClick={jumpToNextMatch}
                       className="absolute right-2 top-1/2 -translate-y-1/2 bg-blue-500 text-white text-xs px-2 py-1 rounded-md active:scale-95"
                     >
                       {matchedIndices.length > 0 ? `${currentMatchIdx + 1}/${matchedIndices.length} ↓` : '0'}
                     </button>
                  )}
               </div>
            </div>

            {renderList.map((row, idx) => {
              const headerText = row.cn?.isHeader ? row.cn.text : row.jp?.isHeader ? row.jp.text : null;
              
              if (headerText) {
                return (
                  <div key={idx} className="my-10 pt-4 border-t border-dashed border-current opacity-30 text-center">
                    <span className="text-xs px-3 py-1 rounded-full border border-current opacity-70 font-mono">
                      {headerText.replace(/---/g, '').trim()}
                    </span>
                  </div>
                );
              }
              
              const isFocused = matchedIndices[currentMatchIdx] === idx;
              const cnSpeakerMatch = searchQuery && row.cn?.speaker?.toLowerCase().includes(searchQuery.toLowerCase());
              const jpSpeakerMatch = searchQuery && row.jp?.speaker?.toLowerCase().includes(searchQuery.toLowerCase());

              return (
                 <div 
                   key={idx} 
                   id={`line-${idx}`}
                   className={`
                     flex flex-col md:flex-row md:gap-4 py-1 border-b border-transparent transition-colors group
                     ${isFocused 
                        ? (theme === 'dark' ? 'bg-blue-900/30 ring-1 ring-blue-500/50' : 'bg-yellow-50 ring-1 ring-yellow-400/50')
                        : 'hover:border-current hover:border-opacity-10'}
                   `}
                 >
                {mode !== 'jp' && (
                      <div className={`flex gap-3 ${mode === 'split' ? 'md:w-1/2' : 'w-full'}`}>
                        {isEditMode ? (
                          <>
                            {/* 编辑模式：始终显示名字和编辑框 */}
                            <div className="w-16 md:w-20 text-right flex-shrink-0 text-xs font-bold pt-2 truncate opacity-60">
                              {editedCnLines[idx]?.speaker || row.jp?.speaker || "旁白"}
                            </div>
                            <textarea
                              className={`flex-1 p-2 rounded border focus:ring-2 focus:ring-emerald-500 outline-none transition-all text-sm ${theme === 'dark' ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-200 text-black'}`}
                              value={editedCnLines[idx]?.text || ""}
                              placeholder="在此输入翻译内容..."
                              onChange={(e) => {
                                const newLines = [...editedCnLines];
                                newLines[idx] = { 
                                  speaker: newLines[idx]?.speaker || row.jp?.speaker || "旁白", 
                                  text: e.target.value,
                                  isHeader: row.jp?.isHeader || row.cn?.isHeader 
                                };
                                setEditedCnLines(newLines);
                              }}
                              rows={Math.max(1, (editedCnLines[idx]?.text || "").split('\n').length)}
                            />
                          </>
                        ) : row.cn ? (
                          <>
                            {/* 阅读模式：有中文时显示内容 */}
                            <div 
                              className={`w-16 md:w-20 text-right flex-shrink-0 text-xs font-bold pt-1 truncate px-1 rounded h-fit ${cnSpeakerMatch ? "ring-2 ring-yellow-400" : ""}`}
                              style={{ 
                                color: SPEAKER_COLOR_MAP[row.cn.speaker] || SPEAKER_COLOR_MAP[row.jp?.speaker || ''] || '',
                                backgroundColor: (SPEAKER_COLOR_MAP[row.cn.speaker] || SPEAKER_COLOR_MAP[row.jp?.speaker || '']) ? 'transparent' : '' 
                              }}
                            >
                              {row.cn.speaker}
                            </div>
                            <div className="flex-1 whitespace-pre-wrap pt-0.5">
                              {renderStyledText(row.cn.text, !!cnSpeakerMatch)}
                            </div>
                          </>
                        ) : (
                          /* 阅读模式：无中文时显示占位 */
                          <div className="flex-1 text-xs opacity-20 italic py-1 border-b border-dashed border-black/5">等待翻译...</div>
                        )}
                      </div>
                    )}
                    
                    {mode !== 'cn' && (
                      <div className={`flex gap-2 ${mode === 'split' ? 'md:w-1/2 md:border-l md:pl-4 border-current border-opacity-10 mt-1 md:mt-0' : 'w-full'}`}>
                         {row.jp ? (
                            <>
                              <div 
                                className={`w-16 md:w-20 text-right flex-shrink-0 text-xs font-bold pt-1 truncate px-1 rounded h-fit ${jpSpeakerMatch ? "ring-2 ring-yellow-400" : "opacity-50"}`}
                                style={{ 
                                  color: SPEAKER_COLOR_MAP[row.jp.speaker] || '',
                                }}
                              >
                                {row.jp.speaker}
                              </div>
                              <div className="flex-1 whitespace-pre-wrap opacity-70 font-sans text-sm">
                                {renderStyledText(row.jp.text, !!jpSpeakerMatch)}
                              </div>
                            </>
                         ) : (
                            <div className="flex-1 text-xs opacity-20 italic py-1">...</div>
                         )}
                      </div>
                    )}
                 </div>
              )
            })}
          </div>
        </div>

        {/* 设置弹窗 */}
        {showSettings && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={()=>setShowSettings(false)}>
            <div className={`w-full max-w-xs p-5 rounded-xl shadow-2xl ${theme==='dark'?'bg-gray-800 border border-gray-700':'bg-white'}`} onClick={e=>e.stopPropagation()}>
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-bold">阅读设置</h3>
                <button onClick={()=>setShowSettings(false)}><X size={18}/></button>
              </div>
              
              <div className="space-y-4 text-sm">
                {/* 移动端设置内备份搜索栏 */}
                <div className="md:hidden">
                   <div className="mb-2 opacity-70">搜索</div>
                <input 
                  type="text" 
                  placeholder="按 Enter 键搜索并跳转..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && jumpToNextMatch()}
                  className={`w-full p-2 rounded border text-sm outline-none ${theme === 'dark' ? 'bg-black/20 border-gray-600' : 'bg-gray-100 border-gray-200'}`}
                />
                </div>

                <div>
                  <div className="mb-2 opacity-70">主题</div>
                  <div className="flex gap-2 justify-center">
                    {[
                      {k:'light',i:Sun, l:'亮色'}, {k:'paper',i:BookOpen, l:'护眼'}, {k:'dark',i:Moon, l:'暗黑'}, {k:'green',i:Leaf, l:'绿色'}
                    ].map(o => (
                      <button key={o.k} onClick={()=>setTheme(o.k as any)} className={`flex-1 py-2 rounded border flex flex-col items-center gap-1 ${theme===o.k ? 'border-blue-500 bg-blue-500/10 text-blue-500' : 'border-transparent bg-black/5'}`}>
                        <o.i size={16}/>
                        <span className="text-[10px]">{o.l}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-1 opacity-70">字号 ({fontSize}px)</div>
                  <input type="range" min="12" max="22" value={fontSize} onChange={e=>setFontSize(Number(e.target.value))} className="w-full"/>
                </div>
                <div>
                  <div className="mb-1 opacity-70">行高 ({lineHeight})</div>
                  <input type="range" min="1.1" max="2.0" step="0.1" value={lineHeight} onChange={e=>setLineHeight(Number(e.target.value))} className="w-full"/>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}