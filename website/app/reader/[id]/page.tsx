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
  headerId?: string;
  isChoice?: boolean;
  choiceLabel?: string;
  choiceTargetId?: string;
};

const parseText = (raw: string): StoryLine[] => {
  if (!raw) return [];
  const lines = raw.split('\n');
  const parsed: StoryLine[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].replace(/^\uFEFF/, '').trim();
    if (!line) continue;

    if (line.startsWith('---')) {
      const headerText = line.replace(/---/g, '').trim();
      const sourceMatch = headerText.match(/Source:\s*([\w\d\-]+)/i);
      const sourceId = sourceMatch ? sourceMatch[1] : '';
      const secMatch = headerText.match(/Section\s*(\d+)/i);
      const secNum = secMatch ? secMatch[1] : '';
      const branchMatch = headerText.match(/(?:Branch|group_)\s*(\d+)/i);
      const branchNum = branchMatch ? branchMatch[1] : '';

      let headerId = '';
      if (sourceId && secNum) {
        headerId = `sec-${sourceId}-${secNum}${branchNum ? `-branch-${branchNum}` : ''}`;
      } else {
        headerId = headerText.replace(/[^a-z0-9]/gi, '-').toLowerCase();
      }

      parsed.push({ speaker: '', text: line, isHeader: true, headerId });
      continue;
    }

    const choiceMatch = line.match(/^选项:\s*【(.+?)】→\s*(\S+)/);
    if (choiceMatch) {
      const choiceLabel = choiceMatch[1];
      const targetGroup = choiceMatch[2];
      const branchNum = targetGroup.replace('group_', '');
      parsed.push({
        speaker: '选项',
        text: `【${choiceLabel}】`,
        isChoice: true,
        choiceLabel,
        choiceTargetId: branchNum,
      });
      continue;
    }

    const separatorIdx = line.search(/[:：﹕︰︓]/);
    if (separatorIdx > 0 && separatorIdx < 20 && !line.startsWith('[')) {
      const rawName = line.substring(0, separatorIdx).trim().replace(/\s+/g, '') || '旁白';
      const content = line.substring(separatorIdx + 1).trim().replace(/\\n/g, '\n');
      parsed.push({ speaker: rawName, text: content });
    } else {
      const content = line.trim().replace(/\\n/g, '\n');
      parsed.push({ speaker: '旁白', text: content });
    }
  }

  const result: StoryLine[] = [];
  for (let i = 0; i < parsed.length; i++) {
    const current = parsed[i];
    if (current.isHeader || current.isChoice) {
      result.push(current);
      continue;
    }
    const last = result.length > 0 ? result[result.length - 1] : null;
    if (last && !last.isHeader && !last.isChoice && last.speaker === current.speaker) {
      last.text += '\n' + current.text;
    } else {
      result.push({ ...current });
    }
  }
  return result;
};

const alignSections = (cn: StoryLine[], jp: StoryLine[]) => {
  const result: { cn?: StoryLine; jp?: StoryLine }[] = [];
  const cnLen = cn.length;
  const jpLen = jp.length;
  const maxLen = Math.max(cnLen, jpLen);

  if (Math.abs(cnLen - jpLen) > 10) {
    const minLen = Math.min(cnLen, jpLen);
    for (let i = 0; i < minLen; i++) {
      result.push({ cn: cn[i], jp: jp[i] });
    }
    for (let i = minLen; i < maxLen; i++) {
      if (i < cnLen) result.push({ cn: cn[i] });
      if (i < jpLen) result.push({ jp: jp[i] });
    }
  } else {
    for (let i = 0; i < maxLen; i++) {
      result.push({ cn: cn[i], jp: jp[i] });
    }
  }
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
  const [mode, setMode] = useState<'cn' | 'split' | 'jp'>('cn');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [fontSize, setFontSize] = useState(15);
  const [lineHeight, setLineHeight] = useState(1.1);
  const [allStories, setAllStories] = useState<Story[]>([]);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedCnLines, setEditedCnLines] = useState<StoryLine[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentMatchIdx, setCurrentMatchIdx] = useState(-1);
  const [matchedIndices, setMatchedIndices] = useState<number[]>([]);

  const initEmptyWithNames = () => {
    if (!jpLines || jpLines.length === 0) return;
    const empty = jpLines.map(line => ({
      ...line,
      speaker: NAME_TRANSLATE_MAP[line.speaker] || line.speaker,
      text: ""
    }));
    setEditedCnLines(empty);
    setMode('split');
  };

  const initWithJpContent = () => {
    if (!jpLines || jpLines.length === 0) return;
    const cloned = jpLines.map(line => ({
      ...line,
      speaker: NAME_TRANSLATE_MAP[line.speaker] || line.speaker,
      text: line.text
    }));
    setEditedCnLines(cloned);
    setMode('split');
  };

  const downloadTxt = () => {
    const linesToExport = editedCnLines.length > 0 ? editedCnLines : cnLines;
    const content = linesToExport.map(l =>
      l.isHeader ? l.text : `${l.speaker}: ${l.text}`
    ).join('\n');
    const blob = new Blob(["\ufeff" + content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${id}_translated.txt`; a.click();
    URL.revokeObjectURL(url);
  };

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

  const submitToCloud = async () => {
    if (editedCnLines.length === 0) return alert("内容为空，无法提交\n\n请先点击「仅填入译名」或「填入日文原文」初始化内容");

    const contentText = editedCnLines.map(l =>
      l.isHeader ? l.text : `${l.speaker}: ${l.text}`
    ).join('\n');

    if (contentText.trim().length < 10) {
      return alert("内容过短，请先编辑翻译内容后再提交");
    }

    let apiError = '';
    try {
      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          story_id: id,
          content: contentText,
          author: 'Anonymous',
        })
      });

      const data = await res.json();

      if (res.ok && data.success) {
        alert("✅ 提交成功！感谢您的贡献，管理员审核后将更新。\n\nKey: " + (data.key || ''));
        return;
      }

      apiError = `HTTP ${res.status}: ${JSON.stringify(data)}`;
    } catch (e: any) {
      apiError = e?.message || '网络错误';
      console.error('API 请求异常:', e);
    }

    console.error('提交失败:', apiError);

    const choice = confirm(
      `⚠️ 在线提交失败\n\n错误详情: ${apiError}\n\n点击「确定」→ 下载TXT文件\n点击「取消」→ 复制到剪贴板`
    );

    if (choice) {
      const BOM = '\uFEFF';
      const blob = new Blob([BOM + contentText], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${id}_submit.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      try {
        await navigator.clipboard.writeText(contentText);
        alert("✅ 已复制到剪贴板！请发送到QQ群 928098518");
      } catch {
        alert("复制失败，请手动复制");
      }
    }
  };

  const currentStory = allStories.find(s => s.id === id);

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
        if (pCn.length > 0 && pJp.length > 0) setMode('split');
        else if (pCn.length === 0) setMode('jp');
        else setMode('cn');
      } finally { setLoading(false); }
    }
    load();
  }, [cnPath, jpPath]);

  const themeStyles = {
    light: "bg-transparent text-gray-900",
    dark: "bg-transparent text-gray-200",
    paper: "bg-transparent text-[#4a4036]",
    green: "bg-transparent text-[#003300]",
  };
  const headerStyles = {
    light: "border-gray-200 bg-white/80 backdrop-blur-md",
    dark: "border-gray-800 bg-[#0f172a]/80 backdrop-blur-md",
    paper: "border-[#e6dfc5] bg-[#f0e6d2]/60 backdrop-blur-md",
    green: "border-[#A8D8B9] bg-[#C7EDCC]/80 backdrop-blur-md",
  };

  const renderList = alignSections(cnLines, jpLines);

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
      const headerRaw = (row.cn?.isHeader ? row.cn.text : row.jp?.isHeader ? row.jp.text : '');
      let headerSearchable = headerRaw.toLowerCase();
      const secNum = headerRaw.match(/Section\s*(\d+)/)?.[1];
      const brNum = headerRaw.match(/Branch\s*(\d+)/)?.[1];
      if (secNum) headerSearchable += ` 第${secNum}节 节${secNum}`;
      if (brNum) headerSearchable += ` 分支${brNum} 路线${brNum} 选项${brNum}`;
      const choiceText = (row.cn?.choiceLabel || row.jp?.choiceLabel || '').toLowerCase();
      const choiceSearchable = choiceText ? `${choiceText} 选项 分支` : '';

      if (cnText.includes(lowerQuery) || cnSpeaker.includes(lowerQuery) ||
          jpText.includes(lowerQuery) || jpSpeaker.includes(lowerQuery) ||
          headerSearchable.includes(lowerQuery) || choiceSearchable.includes(lowerQuery)) {
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

  const jumpToNextMatch = () => {
    if (matchedIndices.length === 0) return;
    const nextIdx = (currentMatchIdx + 1) % matchedIndices.length;
    setCurrentMatchIdx(nextIdx);
    document.getElementById(`line-${matchedIndices[nextIdx]}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const renderStyledText = (text: string, forceHighlight: boolean = false) => {
    const parts = text.split(/(<red>[\s\S]*?<\/red>|<blue>[\s\S]*?<\/blue>|\[textBlack:[\s\S]*?\])/g);
    return parts.map((part, index) => {
      let isRedTag = false;
      let isBlueTag = false;
      let isBlackTag = false;
      let content = part;

      if (part.startsWith('<red>') && part.endsWith('</red>')) {
        content = part.replace(/<\/?red>/g, '');
        isRedTag = true;
      } else if (part.startsWith('<blue>') && part.endsWith('</blue>')) {
        content = part.replace(/<\/?blue>/g, '');
        isBlueTag = true;
      } else if (part.startsWith('[textBlack:') && part.endsWith(']')) {
        content = part.slice(11, -1);
        isBlackTag = true;
      }

      if (searchQuery && (content.toLowerCase().includes(searchQuery.toLowerCase()) || forceHighlight)) {
        const regex = new RegExp(`(${searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        const searchParts = content.split(regex);
        return (
          <span key={index} className={isRedTag ? "text-red-500 font-bold" : isBlueTag ? "text-blue-500 font-bold" : isBlackTag ? "font-black text-gray-900 drop-shadow-sm" : ""}>
            {searchParts.map((sp, i) =>
              regex.test(sp)
                ? <span key={i} className="bg-yellow-200 text-black outline outline-1 outline-yellow-400 rounded px-0.5 shadow-sm mx-0.5">{sp}</span>
                : sp
            )}
          </span>
        );
      }

      return (
        <span key={index} className={isRedTag ? "text-red-500 font-bold" : isBlueTag ? "text-blue-500 font-bold" : isBlackTag ? "font-black text-gray-900 drop-shadow-sm" : ""}>
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
        onClose={() => setSidebarOpen(false)}
        className={sidebarOpen ? "" : "hidden md:flex"}
      />

      <div className="flex-1 flex flex-col min-w-0 relative">
        <header className={`flex items-center justify-between px-4 py-2 border-b z-20 shrink-0 ${headerStyles[theme]}`}>
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => setSidebarOpen(true)} className="md:hidden p-2 -ml-2 rounded hover:bg-black/5">
              <Menu size={20} />
            </button>
            <div className="flex flex-col min-w-0">
              <div className="text-[10px] opacity-50 flex gap-1 whitespace-nowrap">
                <span>{currentStory?.folder || "Loading..."}</span>
              </div>
              <div className="font-bold text-sm flex items-center gap-2 flex-wrap min-w-0">
                <span className="font-mono text-emerald-600 truncate">{id}</span>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {cnPath && (
                    <button
                      onClick={async () => {
                        try {
                          const res = await fetch(cnPath);
                          const text = await res.text();
                          const BOM = '\uFEFF';
                          const blob = new Blob([BOM + text], { type: 'text/plain;charset=utf-8' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `${id}_cn.txt`;
                          a.click();
                          URL.revokeObjectURL(url);
                        } catch (e) {
                          console.error('下载失败:', e);
                        }
                      }}
                      className="flex items-center gap-1 opacity-50 hover:opacity-100 hover:text-green-600 border border-transparent hover:border-green-200 px-1.5 py-0.5 rounded transition-all"
                    >
                      <Download size={14} />
                      <span className="text-[10px]">CN</span>
                    </button>
                  )}
                  {jpPath && (
                    <button
                      onClick={async () => {
                        try {
                          const res = await fetch(jpPath);
                          const text = await res.text();
                          const BOM = '\uFEFF';
                          const blob = new Blob([BOM + text], { type: 'text/plain;charset=utf-8' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `${id}_jp.txt`;
                          a.click();
                          URL.revokeObjectURL(url);
                        } catch (e) {
                          console.error('下载失败:', e);
                        }
                      }}
                      className="flex items-center gap-1 opacity-50 hover:opacity-100 hover:text-blue-600 border border-transparent hover:border-blue-200 px-1.5 py-0.5 rounded transition-all"
                    >
                      <Download size={14} />
                      <span className="text-[10px]">JP</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="hidden md:flex flex-1 max-w-md mx-4 relative group">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Search size={14} className="text-gray-400 group-focus-within:text-blue-500" />
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
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsEditMode(!isEditMode);
                if (!isEditMode && editedCnLines.length === 0) {
                  setEditedCnLines(cnLines.length > 0 ? [...cnLines] : renderList.map(r => ({ speaker: r.jp?.speaker || "", text: "" })));
                }
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition-all z-30 ${isEditMode ? 'bg-emerald-600 text-white shadow-lg' : 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'}`}
            >
              <Leaf size={14} />
              <span className="hidden sm:inline">{isEditMode ? "返回阅读" : "协助汉化"}</span>
            </button>

            <div className={`flex rounded p-0.5 text-[10px] font-bold ${theme === 'dark' ? 'bg-white/10' : 'bg-black/5'}`}>
              {['cn', 'split', 'jp'].map(m => (
                <button key={m} onClick={() => setMode(m as any)} className={`px-2 py-1 rounded ${mode === m ? (theme === 'dark' ? 'bg-gray-700 text-white' : 'bg-white shadow') : 'opacity-40'}`}>
                  {m === 'cn' ? '中' : m === 'jp' ? '日' : '双'}
                </button>
              ))}
            </div>

            <button onClick={() => setShowSettings(true)} className="p-2 rounded hover:bg-black/5 text-gray-500">
              <Settings size={18} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto scroll-smooth p-2 md:p-6 z-10" style={{ fontSize: `${fontSize}px`, lineHeight }}>
          <div className={`max-w-3xl mx-auto pb-32 min-h-screen transition-all duration-500 ease-in-out ${(theme === 'paper' || theme === 'green') ? 'md:bg-white/40 md:shadow-sm md:backdrop-blur-[2px] md:px-12 md:py-8 rounded-lg' : ''}`}>

            {isEditMode && (
              <div className="mb-6 p-4 rounded-xl bg-emerald-50/80 border border-emerald-200 shadow-sm backdrop-blur-sm">
                <div className="flex flex-wrap gap-3 items-center">
                  <span className="text-xs font-bold text-emerald-800 opacity-70 mr-2">初始化:</span>
                  <button onClick={initEmptyWithNames} className="px-3 py-1.5 bg-white border border-emerald-300 text-emerald-700 rounded-lg text-xs font-bold hover:bg-emerald-50 active:scale-95 transition-all">1. 仅填入译名 (空文本)</button>
                  <button onClick={initWithJpContent} className="px-3 py-1.5 bg-white border border-emerald-300 text-emerald-700 rounded-lg text-xs font-bold hover:bg-emerald-50 active:scale-95 transition-all">2. 填入日文原文</button>
                  <div className="h-4 w-px bg-emerald-300 mx-1"></div>
                  <label className="cursor-pointer px-3 py-1.5 bg-blue-50 border border-blue-200 text-blue-700 rounded-lg text-xs font-bold hover:bg-blue-100 transition-all flex items-center gap-1">
                    <span>📂 上传本地 TXT</span>
                    <input type="file" accept=".txt" className="hidden" onChange={handleFileUpload} />
                  </label>
                  <button onClick={downloadTxt} className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-bold shadow hover:bg-blue-700 active:scale-95 transition-all ml-auto">📥 下载当前进度</button>
                  <button onClick={submitToCloud} className="px-3 py-1.5 bg-purple-600 text-white rounded-lg text-xs font-bold shadow hover:bg-purple-700 active:scale-95 transition-all">🚀 提交审核</button>
                </div>
                <div className="mt-2 text-[10px] text-emerald-600/60 pl-1">* 提示：提交审核后，管理员通过后才会更新到网站。请优先下载 TXT 本地保存。</div>
              </div>
            )}

            <div className="md:hidden mb-4 px-1">
              <div className="relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
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

            {!isEditMode && (
              <div className={`mb-0 p-4 rounded-lg border text-sm text-center transition-colors ${theme === 'dark' ? 'bg-white/5 border-white/10 text-gray-400' : 'bg-black/5 border-black/5 text-gray-600'}`}>
                <div className="flex flex-wrap justify-center gap-3 text-xs font-bold">
                  <a href="https://space.bilibili.com/625821?spm_id_from=333.33.0.0" target="_blank" rel="noreferrer" className="hover:text-blue-500 hover:underline transition-colors flex items-center gap-1">
                    <span>🐧群928098518</span>
                  </a>
                  <span>|</span>
                  <Link href="/" className="hover:text-emerald-500 hover:underline transition-colors">🏠 返回首页</Link>
                  <span>|</span>
                  <button
                    onClick={() => {
                      const staffMsg =
                        "(圆环攻略组)贡献清单\n" +
                        "角色：树里、七夕八千代、常暗十七夜、小圆前辈、圆彩、冲浪沙耶香\n" +
                        "活动：万圣城、御影特训、AngelsRoad、XmasString、超越梦、巧匠(复)、AI Memory、DepBlue、决战、假面、那由他、梶叶、激海、Dreamers、Halloween、修行、贝法娜、灰革、传承、SPA、恋△、MVD\n" +
                        "主线II：序章、第2-9章\n" +
                        "支线II：第1-11章\n" +
                        "其他：登录6168、镜层十七夜\n\n" +
                        "※ 以上50项引用自圆环记录攻略组，目前剩余剧情文本将由水银h2oag提供，Staff表会保持更新，本站现由MadeInMagius维护，旨在剧情存档。";
                      alert(staffMsg);
                    }}
                    className="hover:text-pink-500 hover:underline transition-colors"
                  >
                    ❤️ 关于我们
                  </button>
                </div>
                <div className="mt-4 mx-auto w-12 h-1 rounded-full bg-current opacity-20" />
              </div>
            )}

            {renderList.map((row, idx) => {
              const headerLine = row.cn?.isHeader ? row.cn : row.jp?.isHeader ? row.jp : null;

              if (headerLine) {
                const headerText = headerLine.text.replace(/---/g, '').trim();
                const isBranch = headerText.includes('Branch');
                const sectionMatch = headerText.match(/Section\s*(\d+)/);
                const branchMatch = headerText.match(/Branch\s*(\d+)/);

                return (
                  <div
                    key={idx}
                    id={headerLine.headerId}
                    className={`mt-6 mb-4 pt-4 border-t-2 text-center ${isBranch ? 'border-amber-400/50 bg-amber-50/30 rounded-lg py-3' : 'border-dashed border-current opacity-30'}`}
                  >
                    {isBranch ? (
                      <div className="flex flex-col items-center gap-1">
                        <span className={`text-xs px-3 py-1.5 rounded-full font-bold ${theme === 'dark' ? 'bg-amber-900/40 text-amber-300 border border-amber-700' : 'bg-amber-100 text-amber-800 border border-amber-300'}`}>
                          🔀 {sectionMatch ? `第${sectionMatch[1]}节 ` : ''}选项路线 {branchMatch ? branchMatch[1] : ''}
                        </span>
                        <span className="text-[10px] opacity-40 font-mono">{headerText.match(/Source:\s*(.+?)\)/)?.[1] || ''}</span>
                      </div>
                    ) : (
                      <span className="text-xs px-3 py-1 rounded-full border border-current opacity-70 font-mono">{headerText}</span>
                    )}
                  </div>
                );
              }

              const choiceLine = row.cn?.isChoice ? row.cn : row.jp?.isChoice ? row.jp : null;

              if (choiceLine) {
                return (
                  <div key={idx} id={`line-${idx}`} className="my-3 flex justify-center">
                    <button
                      onClick={() => {
                        const branchNum = choiceLine.choiceTargetId;
                        if (!branchNum) return;
                        let currentSectionNum = '';
                        for (let i = idx; i >= 0; i--) {
                          const r = renderList[i];
                          const h = r.cn?.isHeader ? r.cn : r.jp?.isHeader ? r.jp : null;
                          if (h && h.text) {
                            const match = h.text.match(/Section\s*(\d+)/i);
                            if (match) { currentSectionNum = match[1]; break; }
                          }
                        }
                        if (currentSectionNum) {
                          const targetId = `sec-${currentSectionNum}-branch-${branchNum}`;
                          const targetEl = document.getElementById(targetId);
                          if (targetEl) {
                            targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            targetEl.classList.add('ring-4', 'ring-amber-400', 'transition-all', 'duration-500');
                            setTimeout(() => targetEl.classList.remove('ring-4', 'ring-amber-400'), 1500);
                            return;
                          }
                        }
                        for (let i = idx + 1; i < renderList.length; i++) {
                          const r = renderList[i];
                          const h = r.cn?.isHeader ? r.cn : r.jp?.isHeader ? r.jp : null;
                          if (h && (h.text.includes(`Branch ${branchNum}]`) || h.text.includes(`Branch ${branchNum})`))) {
                            const el = document.getElementById(h.headerId || `line-${i}`);
                            el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            return;
                          }
                        }
                      }}
                      className={`px-5 py-2.5 rounded-xl text-sm font-bold transition-all hover:scale-105 active:scale-95 cursor-pointer
                        ${theme === 'dark'
                          ? 'bg-gradient-to-r from-amber-900/60 to-orange-900/60 text-amber-200 border border-amber-700 hover:border-amber-500'
                          : 'bg-gradient-to-r from-amber-50 to-orange-50 text-amber-800 border-2 border-amber-300 hover:border-amber-500 shadow-sm hover:shadow-md'
                        }`}
                    >
                      <span className="mr-1">👆</span>
                      {choiceLine.choiceLabel || choiceLine.text}
                      <span className="ml-2 text-[10px] opacity-50">↓ 点击跳转</span>
                    </button>
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
                  className={`flex flex-col md:flex-row md:gap-4 py-1 border-b border-transparent transition-colors group
                    ${isFocused
                      ? (theme === 'dark' ? 'bg-blue-900/30 ring-1 ring-blue-500/50' : 'bg-yellow-50 ring-1 ring-yellow-400/50')
                      : 'hover:border-current hover:border-opacity-10'}`}
                >
                  {mode !== 'jp' && (
                    <div className={`flex gap-3 ${mode === 'split' ? 'md:w-1/2' : 'w-full'}`}>
                      {isEditMode ? (
                        <>
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
                          <div
                            className={`w-20 md:w-24 text-right flex-shrink-0 text-[11px] leading-tight font-bold pt-1 break-words px-1 rounded h-fit ${cnSpeakerMatch ? "ring-2 ring-yellow-400" : ""}`}
                            style={{
                              color: SPEAKER_COLOR_MAP[row.cn.speaker] ? SPEAKER_COLOR_MAP[row.cn.speaker] : SPEAKER_COLOR_MAP[row.cn.speaker.replace(/\s+/g, '')] || undefined,
                              backgroundColor: (SPEAKER_COLOR_MAP[row.cn.speaker] || SPEAKER_COLOR_MAP[row.cn.speaker.replace(/\s+/g, '')]) ? 'transparent' : ''
                            }}
                          >
                            {row.cn.speaker}
                          </div>
                          <div className="flex-1 whitespace-pre-wrap pt-0.5">
                            {renderStyledText(row.cn.text, !!cnSpeakerMatch)}
                          </div>
                        </>
                      ) : (
                        <div className="flex-1 text-xs opacity-20 italic py-1 border-b border-dashed border-black/5">等待翻译...</div>
                      )}
                    </div>
                  )}

                  {mode !== 'cn' && (
                    <div className={`flex gap-2 ${mode === 'split' ? 'md:w-1/2 md:border-l md:pl-4 border-current border-opacity-10 mt-1 md:mt-0' : 'w-full'}`}>
                      {row.jp ? (
                        <>
                          <div
                            className={`w-20 md:w-24 text-right flex-shrink-0 text-[11px] leading-tight font-bold pt-1 break-words px-1 rounded h-fit ${jpSpeakerMatch ? "ring-2 ring-yellow-400" : "opacity-50"}`}
                            style={{
                              color: SPEAKER_COLOR_MAP[row.jp.speaker] ? SPEAKER_COLOR_MAP[row.jp.speaker] : SPEAKER_COLOR_MAP[row.jp.speaker.replace(/\s+/g, '')] || undefined,
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
              );
            })}
          </div>
        </div>

        {showSettings && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowSettings(false)}>
            <div className={`w-full max-w-xs p-5 rounded-xl shadow-2xl ${theme === 'dark' ? 'bg-gray-800 border border-gray-700' : 'bg-white'}`} onClick={e => e.stopPropagation()}>
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-bold">阅读设置</h3>
                <button onClick={() => setShowSettings(false)}><X size={18} /></button>
              </div>
              <div className="space-y-4 text-sm">
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
                      { k: 'light', i: Sun, l: '亮色' }, { k: 'paper', i: BookOpen, l: '护眼' }, { k: 'dark', i: Moon, l: '暗黑' }, { k: 'green', i: Leaf, l: '绿色' }
                    ].map(o => (
                      <button key={o.k} onClick={() => setTheme(o.k as any)} className={`flex-1 py-2 rounded border flex flex-col items-center gap-1 ${theme === o.k ? 'border-blue-500 bg-blue-500/10 text-blue-500' : 'border-transparent bg-black/5'}`}>
                        <o.i size={16} />
                        <span className="text-[10px]">{o.l}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="mb-1 opacity-70">字号 ({fontSize}px)</div>
                  <input type="range" min="12" max="22" value={fontSize} onChange={e => setFontSize(Number(e.target.value))} className="w-full" />
                </div>
                <div>
                  <div className="mb-1 opacity-70">行高 ({lineHeight})</div>
                  <input type="range" min="1.1" max="2.0" step="0.1" value={lineHeight} onChange={e => setLineHeight(Number(e.target.value))} className="w-full" />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}