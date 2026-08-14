"use client";

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FolderOpen } from 'lucide-react';
import {
  createLocalStoryPayload,
  storeLocalStoryPayload,
} from '@/lib/local-story';

type LocalStoryPickerProps = {
  theme: string;
};

export default function LocalStoryPicker({ theme }: LocalStoryPickerProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const openFiles = async (files: FileList | null) => {
    if (!files?.length) return;

    setBusy(true);
    setError('');
    try {
      const payload = await createLocalStoryPayload(Array.from(files));
      storeLocalStoryPayload(payload);
      router.push(`/reader/${encodeURIComponent(payload.id)}?local=1`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法打开所选文件，请换一个文件重试。');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="relative">
      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept=".json,.txt,application/json,text/plain"
        multiple
        onChange={(event) => void openFiles(event.target.files)}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-bold whitespace-nowrap transition-all disabled:cursor-wait disabled:opacity-60 ${
          theme === 'dark'
            ? 'bg-blue-900/30 border-blue-800 text-blue-300 hover:bg-blue-900/50'
            : theme === 'light' || theme === 'paper'
              ? 'magi-home-light-button'
              : 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100'
        }`}
        title="可选择一个剧情文件，或同时选择一对中日文文件"
      >
        <FolderOpen size={14} />
        {busy ? '正在打开…' : '打开本地剧情'}
      </button>
      {error && (
        <div
          role="alert"
          className={`absolute top-full right-0 mt-2 z-30 w-72 rounded-lg border px-3 py-2 text-xs shadow-lg ${
            theme === 'dark'
              ? 'bg-gray-900 border-red-800 text-red-300'
              : theme === 'light' || theme === 'paper'
                ? 'border-[#a99b80] bg-[#e9e2d2] text-[#6c493c]'
                : 'bg-white border-red-200 text-red-700'
          }`}
        >
          {error}
        </div>
      )}
    </div>
  );
}
