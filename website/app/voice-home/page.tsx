'use client';

import { useEffect } from 'react';

import Home from '../page';

const LABEL_REPLACEMENTS: Readonly<Record<string, string>> = {
  general_voice: '语音',
  '1 主线': '主线',
  '2 Sub': '活动',
  '3 角色': '角色',
  '4 肖像': '肖像',
  '6 语音': '语音',
  '7 Namae': 'Namae',
  '8 Dungeon': '过场动画字幕',
  '10 战斗': '战斗',
};

const replaceCatalogLabels = (root: ParentNode) => {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node instanceof Text) {
      const original = node.nodeValue?.trim() ?? '';
      const replacement = LABEL_REPLACEMENTS[original];
      if (replacement) node.nodeValue = replacement;
    }
    node = walker.nextNode();
  }
};

export default function CatalogLabelHome() {
  useEffect(() => {
    replaceCatalogLabels(document.body);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        for (const added of record.addedNodes) {
          if (added instanceof Element || added instanceof DocumentFragment) {
            replaceCatalogLabels(added);
          } else if (added instanceof Text) {
            const replacement = LABEL_REPLACEMENTS[added.nodeValue?.trim() ?? ''];
            if (replacement) added.nodeValue = replacement;
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return <Home />;
}
