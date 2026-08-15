'use client';

import { useLayoutEffect } from 'react';

import { translateSpeakerName } from '@/app/config/dictionary';

const EXEDRA_CN_SPEAKER_SELECTOR =
  '.exedra-page[lang="zh-Hans"] .reader-font-cn-title';
const SOURCE_ATTRIBUTE = 'magiExedraSpeakerSource';

const isEditableControl = (element: HTMLElement): boolean =>
  element.matches(
    'input, textarea, select, button, [contenteditable="true"], [role="textbox"]',
  );

const localizeSpeakerElement = (element: HTMLElement): void => {
  if (!element.matches(EXEDRA_CN_SPEAKER_SELECTOR) || isEditableControl(element)) {
    return;
  }

  const current = element.textContent?.trim() ?? '';
  if (!current) return;

  const previousSource = element.dataset[SOURCE_ATTRIBUTE] ?? '';
  const previousDisplay = previousSource
    ? translateSpeakerName(previousSource)
    : '';
  const source = previousSource && current === previousDisplay
    ? previousSource
    : current;
  const translated = translateSpeakerName(source);

  if (!translated || translated === source) {
    delete element.dataset[SOURCE_ATTRIBUTE];
    return;
  }

  element.dataset[SOURCE_ATTRIBUTE] = source;
  if (current !== translated) {
    element.textContent = translated;
  }
};

const localizeTree = (root: ParentNode): void => {
  if (root instanceof HTMLElement) {
    localizeSpeakerElement(root);
  }
  root.querySelectorAll<HTMLElement>(EXEDRA_CN_SPEAKER_SELECTOR)
    .forEach(localizeSpeakerElement);
};

/**
 * Official TW Exedra imports deliberately keep the Japanese speaker identity
 * in the proof-bound TXT/JSON. Translate only the rendered Simplified-Chinese
 * speaker label, leaving source bytes, editing fields and the Japanese column
 * untouched.
 */
export default function ExedraSpeakerNameLocalizer() {
  useLayoutEffect(() => {
    localizeTree(document.body);

    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'characterData') {
          const parent = record.target.parentElement;
          if (parent) localizeSpeakerElement(parent);
          continue;
        }
        for (const node of record.addedNodes) {
          if (node instanceof Text) {
            const parent = node.parentElement;
            if (parent) localizeSpeakerElement(parent);
          } else if (node instanceof Element || node instanceof DocumentFragment) {
            localizeTree(node);
          }
        }
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    return () => observer.disconnect();
  }, []);

  return null;
}
