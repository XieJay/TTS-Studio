import { create } from 'zustand'

export interface QueueItem {
  lineId: string
  url: string
  text: string
}

interface PlayerState {
  queue: QueueItem[]
  current: number
  playing: boolean
  play: (queue: QueueItem[], start?: number) => void
  toggle: () => void
  next: () => void
  prev: () => void
  stop: () => void
  setPlaying: (p: boolean) => void
}

export const usePlayer = create<PlayerState>((set, get) => ({
  queue: [],
  current: 0,
  playing: false,
  play: (queue, start = 0) => set({ queue, current: start, playing: true }),
  toggle: () => {
    const { queue, playing } = get()
    if (queue.length === 0) return
    set({ playing: !playing })
  },
  next: () => {
    const { queue, current } = get()
    if (current + 1 < queue.length) set({ current: current + 1, playing: true })
    else set({ playing: false })
  },
  prev: () => {
    const { current } = get()
    if (current > 0) set({ current: current - 1, playing: true })
  },
  stop: () => set({ queue: [], current: 0, playing: false }),
  setPlaying: (p) => set({ playing: p }),
}))
