"use client";
import { X } from 'lucide-react';
import { useDialog } from '@/lib/use-dialog';

const LINKS =[
  {
    href: "https://pd.qq.com/qqweb/qunpro/share?_wv=3&_wwv=128&appChannel=share&inviteCode=2oaXZG3lL1g&attaContentID=e5616861ea2047e3820bf63bb854aa8e&businessType=9&from=181074&biz=ka&mainSourceId=share&subSourceId=others&b=9",
    icon: "QQ", iconClass: "from-[#12b7f5] to-[#0084d1]",
    title: "加入交流群", subtitle: "🐧 群号：928098518",
  },
  {
    href: "https://search.bilibili.com/all?keyword=MadeInMagius",
    icon: "B站", iconClass: "from-[#fb7299] to-[#e04b76]",
    title: "B站 MadeInMagius", subtitle: "关注我的B站动态",
  },
  {
    href: "https://magiaexedralive2dviewer.pages.dev/",
    icon: "L2D", iconClass: "from-[#f59e0b] to-[#d97706]",
    title: "Live2D 模型查看器", subtitle: "在线查看角色 Live2D 动态模型",
  },
  {
    href: "https://magireco-call-search-cn.pages.dev/",
    icon: "搜索", iconClass: "from-[#06b6d4] to-[#0891b2]",
    title: "魔法少女称呼搜索与身高对比", subtitle: "魔法纪录·Magia Exedra",
  },
  {
    href: "https://exedra.wiki/wiki/Characters/zh",
    icon: "WIKI", iconClass: "from-[#8b5cf6] to-[#7c3aed]",
    title: "MAGIA EXEDRA WIKI中文化中...", subtitle: "角色剧情与活动剧情和语音",
  },
];

export default function AboutModal({ isOpen, onClose, theme }: { isOpen: boolean; onClose: () => void; theme: string }) {
  const isDark = theme === 'dark';
  const dialogRef = useDialog<HTMLDivElement>(isOpen, onClose);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-end md:items-center justify-center bg-black/60 backdrop-blur-sm p-0 md:p-4" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-dialog-title"
        tabIndex={-1}
        className={`w-full md:max-w-md md:rounded-2xl rounded-t-2xl overflow-hidden max-h-[85vh] flex flex-col shadow-2xl border transition-all animate-in slide-in-from-bottom-8 duration-300
          ${isDark ? 'bg-gray-900 border-gray-700 text-gray-100' : 'bg-white border-gray-200 text-gray-900'}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="md:hidden flex justify-center pt-3 pb-1"><div className={`w-10 h-1.5 rounded-full ${isDark ? 'bg-gray-700' : 'bg-gray-300'}`} /></div>
        <div className={`flex items-center justify-between px-6 py-4 border-b flex-shrink-0 ${isDark ? 'border-gray-800' : 'border-gray-100'}`}>
          <h2 id="about-dialog-title" className="text-lg font-black bg-gradient-to-r from-emerald-500 to-blue-500 bg-clip-text text-transparent">我的其他工具和动态</h2>
          <button type="button" aria-label="关闭关于窗口" onClick={onClose} className="p-1.5 rounded-lg opacity-50 hover:opacity-100 transition-colors"><X size={20} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-2.5">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} target="_blank" rel="noopener noreferrer" className={`flex items-center gap-3.5 px-4 py-3.5 rounded-xl transition-all active:scale-[0.98] border group ${isDark ? 'bg-white/[0.03] border-white/[0.05] hover:bg-white/[0.08]' : 'bg-gray-50 border-gray-100 hover:bg-white hover:shadow-md hover:border-gray-200'}`}>
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white text-xs font-black flex-shrink-0 bg-gradient-to-br ${link.iconClass} shadow-lg shadow-current/20`}>{link.icon}</div>
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm truncate">{link.title}</div>
                <div className="text-xs opacity-50 mt-0.5 truncate">{link.subtitle}</div>
              </div>
              <span className="text-sm opacity-20 group-hover:opacity-50 group-hover:translate-x-1 transition-all flex-shrink-0">→</span>
            </a>
          ))}
        </div>
        <div className={`px-6 py-3 text-center text-[11px] opacity-30 border-t flex-shrink-0 ${isDark ? 'border-gray-800' : 'border-gray-100'}`}>Made with ❤️ by MadeInMagius</div>
      </div>
    </div>
  );
}
