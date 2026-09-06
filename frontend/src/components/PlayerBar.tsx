import { useEffect, useRef, useState } from 'react'
import { Pause, Play, SkipBack, SkipForward, X } from 'lucide-react'
import { usePlayer } from '../stores/player'

export default function PlayerBar() {
  const { queue, current, playing, toggle, next, prev, stop } = usePlayer()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [progress, setProgress] = useState({ t: 0, d: 0 })

  const item = queue[current]

  // 队列/曲目变化 → 换源并按需播放
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !item) return
    if (audio.dataset.src !== item.url) {
      audio.dataset.src = item.url
      audio.src = item.url
    }
    if (playing) audio.play().catch(() => usePlayer.getState().setPlaying(false))
    else audio.pause()
    document.getElementById(`line-${item.lineId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [item, playing])

  if (!item) return null

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/95 backdrop-blur">
      <audio
        ref={audioRef}
        onEnded={() => next()}
        onTimeUpdate={(e) => {
          const a = e.currentTarget
          setProgress({ t: a.currentTime, d: a.duration || 0 })
        }}
      />
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2.5">
        <div className="flex items-center gap-1">
          <button onClick={prev} disabled={current === 0} className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text disabled:opacity-30">
            <SkipBack size={17} />
          </button>
          <button
            onClick={toggle}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-fg transition hover:opacity-90"
          >
            {playing ? <Pause size={17} /> : <Play size={17} />}
          </button>
          <button onClick={next} disabled={current + 1 >= queue.length} className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text disabled:opacity-30">
            <SkipForward size={17} />
          </button>
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs">
            <span className="text-muted">{current + 1}/{queue.length} · </span>
            {item.text}
          </div>
          <div
            className="mt-1 h-1 cursor-pointer rounded-full bg-surface-2"
            onClick={(e) => {
              const rect = (e.target as HTMLElement).getBoundingClientRect()
              const ratio = (e.clientX - rect.left) / rect.width
              if (audioRef.current && progress.d) audioRef.current.currentTime = ratio * progress.d
            }}
          >
            <div className="h-full rounded-full bg-primary" style={{ width: progress.d ? `${(progress.t / progress.d) * 100}%` : '0%' }} />
          </div>
        </div>
        <span className="shrink-0 font-mono text-xs text-muted">
          {fmt(progress.t)} / {fmt(progress.d)}
        </span>
        <button onClick={stop} title="关闭播放器" className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text">
          <X size={16} />
        </button>
      </div>
    </div>
  )
}

function fmt(sec: number): string {
  if (!Number.isFinite(sec)) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
