#!/usr/bin/env python3
"""Apply visitor-facing copy, dense-layout and long-page performance patches.

The static sources intentionally keep extraction terminology for engineering
traceability.  Production pages should present the archive itself, not the
operator's implementation instructions.  This patch also replaces the eager
whole-document enhancer with an idle-chunked implementation and limits legacy
MutationObservers to root-level application swaps.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


def patch_app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    replacements = [
        (
            "把原 Wiki 的正文、章节、分类、重定向与媒体索引重组为无需账号和数据库的静态资料站。主题入口只负责筛选，不会删减底层内容。",
            "浏览角色、剧情、记忆结晶、Doppel、媒体与Wiki条目。可通过标题、分类和章节快速检索。",
            "portal visitor copy",
        ),
        (
            "浏览全部正文、Game、模板、模块、分类和项目资料",
            "正文、Game、模板、模块、分类与项目资料",
            "all portal copy",
        ),
        (
            "只读静态资料库 · 可读页面与原始渲染HTML并存",
            "魔法纪录中文资料库",
            "footer copy",
        ),
        ("STATIC PRESERVATION READER", "MAGIA RECORD DATABASE", "brand subtitle"),
        ("PRESERVED WIKI ARTICLE", "WIKI ARTICLE", "article eyebrow"),
        ("查看完整原始渲染HTML（保真层）", "原始页面HTML", "raw html label"),
        ("关于数据与长期保存", "关于资料库", "about title"),
        ("保存方式", "资料形式", "about section"),
        (
            "本站从公开文章与分类链接图生成不可编辑的静态快照。构建后只需要普通静态文件托管，不依赖PHP、数据库、账号系统或原Wiki服务器程序。",
            "本站提供魔法纪录中文Wiki条目、角色、语音、Doppel与媒体资料的只读浏览。",
            "about data copy",
        ),
        ("不衰减原则", "页面内容", "about fidelity heading"),
        (
            "每个页面同时保存经过安全处理的可读HTML和完整原始渲染HTML。界面重排、移动端适配和主题切换不会删除底层正文。",
            "Wiki条目保留可读正文、分类、章节、来源与原始页面HTML。",
            "about fidelity copy",
        ),
    ]
    for old, new, label in replacements:
        text = replace_once(text, old, new, label)

    eager = re.compile(r"function enhanceArticle\(\) \{.*?\n\}\n\nasync function articlePage", re.S)
    replacement = r'''function enhanceArticle() {
  const body = document.querySelector('.wiki-document');
  if (!body) return;
  const tables = [...body.querySelectorAll('table')];
  const images = [...body.querySelectorAll('img')];
  const widthNodes = [...body.querySelectorAll('[width]')];
  let tableIndex = 0;
  let imageIndex = 0;
  let widthIndex = 0;

  const schedule = (callback) => {
    if ('requestIdleCallback' in window) requestIdleCallback(callback, { timeout: 220 });
    else setTimeout(() => callback({ timeRemaining: () => 8, didTimeout: true }), 0);
  };

  const processTable = (table) => {
    table.removeAttribute('width');
    if (table.parentElement?.classList.contains('table-viewport')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-viewport';
    table.parentNode?.insertBefore(wrapper, table);
    wrapper.appendChild(table);
  };

  const processImage = (image) => {
    image.removeAttribute('width');
    image.removeAttribute('height');
    image.removeAttribute('style');
    image.classList.add('reader-image');
    image.loading = 'lazy';
    image.decoding = 'async';
    image.tabIndex = 0;
    const classify = () => {
      if (image.naturalWidth <= 180 && image.naturalHeight <= 180) image.classList.add('reader-icon');
      if (image.closest('table')) image.classList.add('table-image');
    };
    if (image.complete) classify(); else image.addEventListener('load', classify, { once: true });
    image.addEventListener('error', () => image.classList.add('image-failed'), { once: true });
  };

  const work = (deadline) => {
    let processed = 0;
    while ((deadline.timeRemaining() > 2 || deadline.didTimeout) && processed < 36) {
      if (tableIndex < tables.length) processTable(tables[tableIndex++]);
      else if (imageIndex < images.length) processImage(images[imageIndex++]);
      else if (widthIndex < widthNodes.length) widthNodes[widthIndex++].removeAttribute('width');
      else {
        body.dataset.enhanced = 'true';
        return;
      }
      processed += 1;
    }
    schedule(work);
  };

  /* Process the first visible items synchronously, then yield the main thread. */
  tables.slice(0, 6).forEach((table) => { processTable(table); tableIndex += 1; });
  images.slice(0, 10).forEach((image) => { processImage(image); imageIndex += 1; });
  schedule(work);
}

async function articlePage'''
    text, count = eager.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"article enhancer replacement count: {count}")
    path.write_text(text, encoding="utf-8")


def patch_structured(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    replacements = [
        ("STRUCTURED ARCHIVE & READER", "MAGIA RECORD DATABASE", "structured brand"),
        (
            "角色与语音来自原始人物页面的结构化提取 · Wiki正文独立保存",
            "人物、语音与Wiki资料",
            "structured footer",
        ),
        ("STRUCTURED CHARACTER ARCHIVE", "CHARACTER DATABASE", "character eyebrow"),
        (
            "这里不是Wiki文章关键词筛选，而是从全部“人物信息”表直接生成的角色图鉴。活动、歌曲、目录页不会进入人物列表；组织可通过筛选单独查看。",
            "按人物信息浏览中文名、日文名、声优、设定、关系与角色语音。组织资料可通过筛选单独查看。",
            "character visitor copy",
        ),
        ("结构化图鉴", "资料图鉴", "character result label"),
        (
            "从原Wiki语音组件的原始 <code>data-bind</code> 中恢复MP3地址，并保留中文译文、日文原文、服装、场景分类和语音槽位。播放器按需加载，不会在进入页面时批量下载音频。",
            "按人物浏览角色语音、中文译文、日文原文、服装与场景分类。音频在点击播放时加载。",
            "voice visitor copy",
        ),
        ("可播放语音档案", "语音资料", "voice result label"),
        ("结构化资料读取失败", "资料读取失败", "structured error"),
    ]
    for old, new, label in replacements:
        text = replace_once(text, old, new, label)
    old_observer = "structuredObserver.observe(structuredApp, { childList: true, subtree: true });"
    if old_observer in text:
        text = text.replace(old_observer, "structuredObserver.observe(structuredApp, { childList: true, subtree: false });", 1)
    path.write_text(text, encoding="utf-8")


def patch_doppel(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    replacements = [
        ("STRUCTURED ARCHIVE & READER", "MAGIA RECORD DATABASE", "doppel brand"),
        (
            "174条Doppel来自人物页面原始信息表 · 可读图鉴与Wiki正文并存",
            "174条Doppel资料",
            "doppel footer",
        ),
        ("STRUCTURED DOPPEL ARCHIVE", "DOPPEL DATABASE", "doppel eyebrow"),
        (
            "从174个人物页面的Doppel信息表直接提取，保留角色、名称、魔女文字、感情称号、姿态、原案/监修以及中日双语说明。这里不是正文关键词筛选。",
            "浏览174条Doppel资料，包括关联角色、名称、魔女文字、感情称号、姿态、原案/监修与中日说明。",
            "doppel visitor copy",
        ),
        ("结构化图鉴", "Doppel资料", "doppel result label"),
    ]
    for old, new, label in replacements:
        text = replace_once(text, old, new, label)
    old_observer = "doppelObserver.observe(doppelApp, { childList: true, subtree: true });"
    if old_observer in text:
        text = text.replace(old_observer, "doppelObserver.observe(doppelApp, { childList: true, subtree: false });", 1)
    path.write_text(text, encoding="utf-8")


def patch_index(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('aria-live="polite"', 'aria-live="off"')
    if "/dense-reader.css" not in text:
        marker = '  <link rel="stylesheet" href="/doppel-ui.css?v=5.3">'
        if marker not in text:
            raise RuntimeError("doppel stylesheet marker missing")
        text = text.replace(marker, marker + '\n  <link rel="stylesheet" href="/dense-reader.css?v=6.0">', 1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    patch_app(root / "app.js")
    patch_structured(root / "structured-ui.js")
    patch_doppel(root / "doppel-ui.js")
    patch_index(root / "index.html")
    print("dense reader patch applied")


if __name__ == "__main__":
    main()
