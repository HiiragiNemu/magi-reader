'use client';

import { useEffect } from 'react';

import Home from '../page';

const replaceVoiceLabels = (root: ParentNode) => {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const replacements: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    if (node instanceof Text && node.nodeValue?.trim() === 'general_voice') {
      replacements.push(node);
    }
    node = walker.nextNode();
  }
  for (const text of replacements) text.nodeValue = '语音';
};

export default function VoiceEnabledHome() {
  useEffect(() => {
    replaceVoiceLabels(document.body);
    const observer = new MutationObserver(records => {
      for (const record of records) {
        for (const added of record.addedNodes) {
          if (added instanceof Element || added instanceof DocumentFragment) {
            replaceVoiceLabels(added);
          } else if (added instanceof Text && added.nodeValue?.trim() === 'general_voice') {
            added.nodeValue = '语音';
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return <Home />;
}
