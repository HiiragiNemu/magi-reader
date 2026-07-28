'use client';

import { useEffect } from 'react';

const REPLACEMENTS: Readonly<Record<string, string>> = {
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

const normalizeTextNode = (node: Text) => {
  const replacement = REPLACEMENTS[node.nodeValue?.trim() ?? ''];
  if (replacement) node.nodeValue = replacement;
};

const normalizeTree = (root: ParentNode) => {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node instanceof Text) normalizeTextNode(node);
    node = walker.nextNode();
  }
};

export default function CategoryLabelNormalizer() {
  useEffect(() => {
    normalizeTree(document.body);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        for (const added of record.addedNodes) {
          if (added instanceof Text) {
            normalizeTextNode(added);
          } else if (added instanceof Element || added instanceof DocumentFragment) {
            normalizeTree(added);
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return null;
}
