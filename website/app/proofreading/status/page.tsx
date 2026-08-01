'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';

import {
  PROOFREADING_STATUS_LABELS,
  type ProofreadingPublicStatus,
} from '@/lib/proofreading';
import {
  PROOFREADING_RECEIPTS_KEY,
  type StoredProofreadingReceipt as StoredReceipt,
} from '@/lib/proofreading-client';

type ReceiptState = StoredReceipt & {
  loading?: boolean;
  error?: string;
  remote?: ProofreadingPublicStatus;
};

const readReceipts = (): StoredReceipt[] => {
  try {
    const raw = localStorage.getItem(PROOFREADING_RECEIPTS_KEY);
    const value: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is StoredReceipt => {
      if (!item || typeof item !== 'object') return false;
      const record = item as Record<string, unknown>;
      return (
        typeof record.id === 'string' &&
        typeof record.receipt === 'string' &&
        typeof record.storyId === 'string' &&
        typeof record.nickname === 'string' &&
        typeof record.submittedAt === 'string'
      );
    });
  } catch {
    return [];
  }
};

const writeReceipts = (receipts: StoredReceipt[]) => {
  localStorage.setItem(PROOFREADING_RECEIPTS_KEY, JSON.stringify(receipts));
};

export default function ProofreadingStatusPage() {
  const [receipts, setReceipts] = useState<ReceiptState[]>([]);

  const refreshOne = useCallback(async (receipt: StoredReceipt) => {
    setReceipts((current) =>
      current.map((item) =>
        item.id === receipt.id
          ? { ...item, loading: true, error: '' }
          : item,
      ),
    );
    try {
      const response = await fetch(
        `/api/submit?id=${encodeURIComponent(receipt.id)}&receipt=${encodeURIComponent(receipt.receipt)}`,
        { cache: 'no-store' },
      );
      const payload = await response.json() as ProofreadingPublicStatus & {
        error?: string;
      };
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      setReceipts((current) =>
        current.map((item) =>
          item.id === receipt.id
            ? { ...item, loading: false, remote: payload, error: '' }
            : item,
        ),
      );
    } catch (error) {
      setReceipts((current) =>
        current.map((item) =>
          item.id === receipt.id
            ? {
                ...item,
                loading: false,
                error: error instanceof Error ? error.message : '查询失败',
              }
            : item,
        ),
      );
    }
  }, []);

  useEffect(() => {
    const stored = readReceipts();
    setReceipts(stored);
    for (const receipt of stored) void refreshOne(receipt);
  }, [refreshOne]);

  const removeReceipt = (id: string) => {
    setReceipts((current) => {
      const next = current.filter((item) => item.id !== id);
      writeReceipts(next);
      return next;
    });
  };

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-8 text-gray-900">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">我的校对投稿</h1>
          <p className="mt-1 text-sm text-gray-500">
            回执只保存在当前浏览器。清除浏览器数据后无法恢复，请另行保存审核编号和回执。
          </p>
        </div>
        <Link href="/" className="rounded-lg border px-3 py-2 text-sm hover:bg-gray-50">
          返回剧情目录
        </Link>
      </div>

      {receipts.length === 0 ? (
        <div className="rounded-xl border border-dashed p-8 text-center text-gray-500">
          当前浏览器没有保存过校对投稿。
        </div>
      ) : (
        <div className="space-y-4">
          {receipts.map((item) => {
            const status = item.remote?.status;
            return (
              <article key={item.id} className="rounded-xl border bg-white p-4 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-sm font-bold text-emerald-700">
                      {item.storyId}
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {item.nickname} · {new Date(item.submittedAt).toLocaleString('zh-CN')}
                    </div>
                    <div className="mt-1 break-all font-mono text-[11px] text-gray-400">
                      {item.id}
                    </div>
                  </div>
                  <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
                    {item.loading
                      ? '查询中…'
                      : status
                        ? PROOFREADING_STATUS_LABELS[status]
                        : '尚未查询'}
                  </span>
                </div>

                {item.remote?.public_message && (
                  <p className="mt-3 rounded-lg bg-blue-50 p-3 text-sm text-blue-900">
                    审核回复：{item.remote.public_message}
                  </p>
                )}
                {item.remote?.pull_request?.url && (
                  <a
                    href={item.remote.pull_request.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 inline-block text-sm font-bold text-blue-700 underline"
                  >
                    查看 GitHub 校对 PR #{item.remote.pull_request.number}
                  </a>
                )}
                {item.error && (
                  <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                    {item.error}
                  </p>
                )}

                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    onClick={() => void refreshOne(item)}
                    disabled={item.loading}
                    className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
                  >
                    <RefreshCw size={14} />刷新状态
                  </button>
                  <button
                    type="button"
                    onClick={() => removeReceipt(item.id)}
                    className="flex items-center gap-1 rounded-lg border px-3 py-2 text-xs text-gray-600 hover:bg-gray-50"
                  >
                    <Trash2 size={14} />从本机移除
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </main>
  );
}
