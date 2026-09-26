"use client";

import { useRef } from "react";
import { fmtClock } from "@/lib/format";

export function TranscriptWithAudio({
  segments,
  audioUrl,
}: {
  segments: Array<{ sequence: number; speaker_role: string; start_seconds: number; raw_text: string; roman_urdu_text: string }>;
  audioUrl: string | null;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);

  function seek(t: number) {
    if (audioRef.current) {
      audioRef.current.currentTime = t;
      audioRef.current.play().catch(() => {});
    }
  }

  return (
    <div>
      {audioUrl ? (
        <audio ref={audioRef} controls preload="metadata" src={audioUrl} className="w-full" aria-label="Call recording" />
      ) : (
        <p className="rounded bg-slate-100 p-3 text-sm text-slate-600">Recording deleted under 15-day retention policy. Transcript and report retained.</p>
      )}
      <ol className="mt-4 space-y-2">
        {segments.map((s) => (
          <li key={s.sequence} className="rounded border p-2 text-sm">
            <button onClick={() => seek(s.start_seconds)} className="font-mono text-xs text-blue-700 hover:underline" aria-label={`Seek to ${fmtClock(s.start_seconds)}`}>
              {fmtClock(s.start_seconds)}
            </button>
            <span className="ml-2 font-medium">{s.speaker_role}</span>
            <p className="mt-1">{s.roman_urdu_text || s.raw_text}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
