"use client";

import FloatingWindow from '@/components/FloatingWindow';

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
    title: "MAGIA EXEDRA WIKI中文化中...", subtitle: "角色剧情、活动剧情与语音",
  },
];

export default function AboutModal({ isOpen, onClose, theme }: { isOpen: boolean; onClose: () => void; theme: string }) {
  const isDark = theme === 'dark';
  return (
    <FloatingWindow
      isOpen={isOpen}
      onClose={onClose}
      theme={theme}
      title="我的其他工具和动态"
      titleId="about-dialog-title"
      systemLabel="SYS://MAGIREADER.LINKS"
      initialOffset={{ x: 84, y: 62 }}
      className="magi-about-window"
      bodyClassName="space-y-2.5 p-4"
      footer="Made with ♥ by MadeInMagius"
    >
      {LINKS.map((link) => (
        <a
          key={link.href}
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          className={`magi-floating-link group flex items-center gap-3.5 border px-4 py-3.5 transition-all active:scale-[0.99] ${isDark ? 'border-white/[0.08] bg-white/[0.04]' : ''}`}
        >
          <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center bg-gradient-to-br text-xs font-black text-white ${link.iconClass}`}>{link.icon}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-bold">{link.title}</div>
            <div className="mt-0.5 truncate text-xs opacity-55">{link.subtitle}</div>
          </div>
          <span className="flex-shrink-0 text-sm opacity-30 transition-all group-hover:translate-x-1 group-hover:opacity-60">→</span>
        </a>
      ))}
    </FloatingWindow>
  );
}
