export const UTF8_BOM_BYTES = Uint8Array.of(0xef, 0xbb, 0xbf);
export const DOWNLOAD_URL_REVOKE_DELAY_MS = 30_000;

const LEADING_BOM_PATTERN = /^\uFEFF+/u;

export const safeDownloadFilename = (
  value: string,
  fallback = 'story.txt',
): string =>
  value
    .replace(/[<>:"/\\|?*\u0000-\u001F]/gu, '-')
    .replace(/\s+/gu, ' ')
    .replace(/[. ]+$/gu, '')
    .trim() || fallback;

export const createUtf8DownloadBlob = (
  content: string,
  filename: string,
): Blob => {
  const normalizedFilename = safeDownloadFilename(filename);
  const isText = normalizedFilename.toLowerCase().endsWith('.txt');
  const body = content.replace(LEADING_BOM_PATTERN, '');

  if (isText) {
    const mobileCompatibleBody = body.replace(/\r\n?|\n/gu, '\r\n');
    // Some Android and iOS text editors still guess GBK/ANSI for a bare UTF-8
    // TXT. Supplying the BOM as its literal byte sequence makes the encoding
    // unambiguous and avoids depending on Blob's handling of U+FEFF.
    // CRLF also keeps the file readable in older mobile/Windows editors while
    // the uploader normalizes it back to the canonical LF representation.
    return new Blob([UTF8_BOM_BYTES, mobileCompatibleBody], {
      type: 'text/plain;charset=utf-8',
    });
  }

  return new Blob([body], {
    type: normalizedFilename.toLowerCase().endsWith('.json')
      ? 'application/json;charset=utf-8'
      : 'application/octet-stream',
  });
};

export const triggerBlobDownload = (
  blob: Blob,
  filename: string,
): void => {
  const safeFilename = safeDownloadFilename(filename);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = safeFilename;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  // Mobile browsers can defer consuming a Blob URL until their download UI
  // has opened. Revoking it after 100 ms (the old behavior) could therefore
  // race the download. Keep it bounded, but long enough for that hand-off.
  window.setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_REVOKE_DELAY_MS);
};

export const triggerUtf8Download = (
  content: string,
  filename: string,
): void => {
  const safeFilename = safeDownloadFilename(filename);
  triggerBlobDownload(
    createUtf8DownloadBlob(content, safeFilename),
    safeFilename,
  );
};
