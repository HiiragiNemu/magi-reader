'use client';

import { LoaderCircle, Square, Volume2 } from 'lucide-react';
import { useSyncExternalStore } from 'react';

import { parseVoiceCue } from '@/lib/audio/voice-cue';
import { voicePlaybackController } from '@/lib/audio/voice-player';

export interface VoicePlayButtonProps {
  cueId?: string | null;
  className?: string;
  label?: string;
}

export function VoicePlayButton({
  cueId,
  className = '',
  label = '播放语音',
}: VoicePlayButtonProps) {
  const state = useSyncExternalStore(
    voicePlaybackController.subscribe,
    voicePlaybackController.getSnapshot,
    voicePlaybackController.getServerSnapshot,
  );
  if (!cueId || !parseVoiceCue(cueId)) return null;

  const isCurrent = state.cueId === cueId;
  const isLoading = isCurrent && state.status === 'loading';
  const isPlaying = isCurrent && state.status === 'playing';
  const accessibleLabel = isLoading
    ? '停止加载语音'
    : isPlaying
      ? '停止语音'
      : label;

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        className={`inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-sky-300 bg-sky-50 px-3 py-2 text-sm font-semibold text-sky-800 transition hover:bg-sky-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-wait ${className}`}
        aria-label={`${accessibleLabel}：${cueId}`}
        aria-pressed={isPlaying}
        disabled={false}
        onClick={() => {
          void voicePlaybackController.toggle(cueId);
        }}
      >
        {isLoading ? (
          <LoaderCircle aria-hidden className="h-4 w-4 animate-spin" />
        ) : isPlaying ? (
          <Square aria-hidden className="h-4 w-4 fill-current" />
        ) : (
          <Volume2 aria-hidden className="h-4 w-4" />
        )}
        <span>{isLoading ? '加载中' : isPlaying ? '停止' : label}</span>
      </button>
      {isCurrent && state.status === 'error' && state.error ? (
        <span className="max-w-72 text-xs text-red-700" role="status">
          {state.error}
        </span>
      ) : null}
    </span>
  );
}

export default VoicePlayButton;
