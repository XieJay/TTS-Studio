import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AudioLines, BookA, ChevronDown, ChevronUp, CircleCheck, CircleDashed, Download, Loader2, Play,
  Settings2, Sparkles, Trash2, TriangleAlert,
} from 'lucide-react'
import { useParams } from 'react-router-dom'
import { apiAudio, apiGet, apiSend } from '../api/client'
import type { ProviderInfo } from '../api/types'
import PlayerBar from '../components/PlayerBar'
import { Badge, Button, Card, Modal, Select, Slider, TextInput } from '../components/ui'
import { usePlayer, type QueueItem } from '../stores/player'

interface LineRow {
  id: string
  idx: number
  role_id: string
  text: string
  emotion: string
  instruct: string
  speed: number | null
  pitch: number | null
  volume: number | null
  gap_after_ms: number | null
  status: 'pending' | 'synthesizing' | 'done' | 'failed'
  audio_path: string
  duration_ms: number | null
  error: string
}

interface TaskData {
  task: {
    id: string
    title: string
    mode: string
    voice_id: string
    global_params: { provider_id?: string; speed?: number; volume?: number }
  }
  lines: LineRow[]
  roles: { id: string; name: string; color: string; voice_id: string; params: string | object }[]
}

const EMOTIONS = ['', '平静', '庄重', '开心', '悲伤', '愤怒', '惊讶', '恐惧']

export default function Studio() {
  const { taskId = '' } = useParams()
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<string>('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [synthLineId, setSynthLineId] = useState<string>('')
  const [notice, setNotice] = useState('')
  const [showExport, setShowExport] = useState(false)
  const [showAnalyze, setShowAnalyze] = useState(false)
  const [showPronunciation, setShowPronunciation] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['task', taskId],
    queryFn: () => apiGet<TaskData>(`/api/tasks/${taskId}`),
  })
  const { data: voices = [] } = useQuery({
    queryKey: ['voices'],
    queryFn: () => apiGet<{ voices: { id: string; name: string }[] }>('/api/voices').then((r) => r.voices),
  })
  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['task', taskId] })

  // 单句合成：记录在合成的那一行做按钮 loading；期间禁用其他行，防止重复点击/并发请求
  const synthSingle = useMutation({
    mutationFn: (lineId: string) => {
      setSynthLineId(lineId)
      return apiSend(`/api/jobs/lines/${lineId}/synthesize`, 'POST')
    },
    onSuccess: () => invalidate(),
    onError: (e) => setNotice(e instanceof Error ? e.message : String(e)),
    onSettled: () => setSynthLineId(''),
  })

  const updateTask = useMutation({
    mutationFn: (patch: Record<string, unknown>) => apiSend(`/api/tasks/${taskId}`, 'PUT', patch),
    onSuccess: () => invalidate(),
  })

  const updateLine = useMutation({
    mutationFn: ({ lineId, patch }: { lineId: string; patch: Record<string, unknown> }) =>
      apiSend(`/api/tasks/${taskId}/lines/${lineId}`, 'PUT', patch),
    onSuccess: () => invalidate(),
  })

  // 离开页面时关闭 SSE
  useEffect(() => () => esRef.current?.close(), [])

  if (isLoading) return <div className="py-20 text-center text-sm text-muted">加载任务…</div>
  if (error || !data) return <div className="py-20 text-center text-sm text-danger">任务加载失败</div>

  const { task, lines, roles } = data
  const isDialogue = task.mode === 'dialogue'
  const providerId = task.global_params.provider_id ?? 'edge'
  const providerName = providers.find((p) => p.id === providerId)?.name ?? providerId
  const voiceName = voices.find((v) => v.id === task.voice_id)?.name ?? '未绑定'
  const doneCount = lines.filter((l) => l.status === 'done').length
  const jobRunning = lines.some((l) => l.status === 'synthesizing')
  const doneLines = lines.filter((l) => l.status === 'done')

  const lineUrl = (l: LineRow) => `/audio/tasks/${l.audio_path}`
  const roleMap = new Map(roles.map((r) => [r.id, { name: r.name, color: r.color }]))
  const playQueue = (startIdx: number) => {
    const queue: QueueItem[] = doneLines.map((l) => ({ lineId: l.id, url: lineUrl(l), text: l.text }))
    const pos = queue.findIndex((q) => q.lineId === doneLines[startIdx]?.id)
    usePlayer.getState().play(queue, Math.max(0, pos))
  }

  // ---- 批量合成（SSE） ----
  const startBatch = async (lineIds?: string[], force = false) => {
    setNotice('')
    const url = force ? '/api/jobs/resynthesize' : '/api/jobs/synthesize'
    const r = await apiSend<{ job_id: string | null; message?: string }>(url, 'POST', {
      task_id: taskId,
      line_ids: lineIds && lineIds.length > 0 ? lineIds : undefined,
    })
    if (!r.job_id) {
      setNotice(r.message ?? '没有需要合成的句子')
      return
    }
    esRef.current?.close()
    const es = new EventSource(`/api/jobs/${r.job_id}/events`)
    esRef.current = es
    es.onmessage = (ev) => {
      const payload = JSON.parse(ev.data)
      if (payload.type === 'job_done') {
        es.close()
        invalidate()
        setNotice('合成完成，可以播放与导出了')
      } else if (payload.type === 'line_done' || payload.type === 'line_failed' || payload.type === 'line_start') {
        // 局部更新行状态，避免整页刷新闪烁
        queryClient.setQueryData<TaskData>(['task', taskId], (old) => {
          if (!old) return old
          return {
            ...old,
            lines: old.lines.map((l) =>
              l.id === payload.line_id
                ? {
                    ...l,
                    status:
                      payload.type === 'line_start' ? 'synthesizing'
                      : payload.type === 'line_done' ? 'done'
                      : 'failed',
                    error: payload.error ?? '',
                    duration_ms: payload.duration_ms ?? l.duration_ms,
                  }
                : l,
            ),
          }
        })
      }
    }
    es.onerror = () => {
      es.close()
      invalidate()
    }
    invalidate()
  }

  const exportFile = async (kind: 'mp3' | 'wav' | 'zip' | 'srt') => {
    setNotice('')
    try {
      let blob: Blob
      let name: string
      if (kind === 'mp3' || kind === 'wav') {
        const r = await apiAudio(`/api/tasks/${taskId}/merge`, { format: kind })
        blob = r.blob
        name = `${task.title}_合并.${kind}`
      } else {
        const resp = await fetch(`/api/tasks/${taskId}/export?format=${kind}`)
        if (!resp.ok) throw new Error((await resp.json()).detail ?? '导出失败')
        blob = await resp.blob()
        name = kind === 'zip' ? `${task.title}.zip` : `${task.title}.srt`
      }
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = name
      a.click()
      setShowExport(false)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className={`pb-24 ${isDialogue ? 'grid items-start gap-4 xl:grid-cols-[250px_1fr]' : 'space-y-4'}`}>
      {isDialogue && (
        <div className="space-y-3 xl:sticky xl:top-20">
          <h2 className="text-sm font-medium text-muted">角色（{roles.length}）</h2>
          {roles.map((r) => (
            <RoleCard
              key={r.id}
              role={r}
              voices={voices}
              onSave={(patch) => apiSend(`/api/tasks/${taskId}/roles/${r.id}`, 'PUT', patch).then(invalidate)}
            />
          ))}
          {roles.every((r) => !r.voice_id) && (
            <p className="text-xs text-warn">请为每个角色绑定音色（可在音色库复刻）。</p>
          )}
        </div>
      )}
      <div className="space-y-4">
      {/* 顶部工具栏 */}
      <Card className="flex flex-wrap items-center gap-3">
        <input
          className="min-w-40 flex-1 bg-transparent text-lg font-semibold outline-none"
          value={task.title}
          onChange={(e) => queryClient.setQueryData<TaskData>(['task', taskId], (o) => (o ? { ...o, task: { ...o.task, title: e.target.value } } : o))}
          onBlur={() => updateTask.mutate({ title: task.title })}
        />
        <Badge tone={task.mode === 'dialogue' ? 'primary' : 'muted'}>
          {task.mode === 'dialogue' ? '多角色对话' : '单音色稿件'}
        </Badge>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowAnalyze(true)}>
            <Sparkles size={15} /> AI 语境分析
          </Button>
          <Button variant="outline" onClick={() => setShowPronunciation(true)}>
            <BookA size={15} /> 发音规则
          </Button>
          <Button loading={jobRunning} onClick={() => startBatch()}>
            {jobRunning ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />} 全部合成
          </Button>
          <div className="relative">
            <Button variant="outline" onClick={() => setShowExport(!showExport)} disabled={doneCount === 0}>
              <Download size={15} /> 导出
            </Button>
            {showExport && (
              <div className="absolute right-0 z-30 mt-1 w-44 rounded-lg border border-border bg-surface py-1 shadow-xl">
                {(['mp3', 'wav', 'zip', 'srt'] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => exportFile(k)}
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-2"
                  >
                    {k === 'mp3' && '合并音频 MP3'}
                    {k === 'wav' && '合并音频 WAV'}
                    {k === 'zip' && '打包 ZIP（含逐句+SRT）'}
                    {k === 'srt' && 'SRT 字幕'}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* 任务级设置条 */}
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-xs text-muted">音色</span>
          <Select
            size="sm"
            className="min-w-28"
            value={task.voice_id}
            onChange={(v) => updateTask.mutate({ voice_id: v })}
            options={[{ value: '', label: '未绑定' }, ...voices.map((v) => ({ value: v.id, label: v.name }))]}
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs text-muted">引擎</span>
          <Select
            size="sm"
            className="min-w-36"
            value={providerId}
            onChange={(v) => updateTask.mutate({ global_params: { provider_id: v } })}
            options={providers
              .filter((p) => p.configured || p.id === providerId)
              .map((p) => ({ value: p.id, label: p.configured ? p.name : `${p.name}（未配置）` }))}
          />
        </label>
        <span className="text-xs text-muted">
          {doneCount}/{lines.length} 句已合成 · 换音色或引擎后句子会重置为待合成
        </span>
        {notice && <span className="ml-auto text-xs text-primary">{notice}</span>}
      </Card>

      {/* 批量操作条 */}
      {selected.size > 0 && (
        <Card className="flex items-center gap-3 py-2.5">
          <span className="text-sm">已选 {selected.size} 句</span>
          <Button variant="outline" className="text-xs" onClick={() => startBatch([...selected])}>合成选中</Button>
          <Button
            variant="ghost"
            className="text-xs"
            onClick={() => {
              startBatch([...selected], true)
            }}
          >
            强制重做选中
          </Button>
          <Button variant="ghost" className="ml-auto text-xs" onClick={() => setSelected(new Set())}>取消选择</Button>
        </Card>
      )}

      {/* 全选 + 句子列表 */}
      {lines.length > 0 && (
        <label className="flex w-fit cursor-pointer select-none items-center gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={selected.size === lines.length}
            ref={(el) => {
              if (el) el.indeterminate = selected.size > 0 && selected.size < lines.length
            }}
            onChange={(e) => setSelected(e.target.checked ? new Set(lines.map((l) => l.id)) : new Set())}
          />
          全选句子{selected.size > 0 ? `（已选 ${selected.size}/${lines.length}）` : `（共 ${lines.length} 句）`}
        </label>
      )}
      <div className="space-y-2">
        {lines.map((l, i) => (
          <LineCard
            key={l.id}
            line={l}
            index={i}
            isFirst={i === 0}
            isLast={i === lines.length - 1}
            expanded={expanded === l.id}
            selected={selected.has(l.id)}
            synthRunning={synthLineId === l.id}
            synthDisabled={synthLineId !== ''}
            providerCaps={providers.find((p) => p.id === providerId)?.capabilities}
            roleInfo={l.role_id ? roleMap.get(l.role_id) : undefined}
            onToggleSelect={() => {
              const s = new Set(selected)
              if (s.has(l.id)) s.delete(l.id)
              else s.add(l.id)
              setSelected(s)
            }}
            onExpand={() => setExpanded(expanded === l.id ? '' : l.id)}
            onPlay={() => playQueue(i)}
            onSynth={() => synthSingle.mutate(l.id)}
            onMove={(dir) => apiSend(`/api/tasks/${taskId}/lines/${l.id}/move`, 'POST', { direction: dir }).then(invalidate)}
            onDelete={() => apiSend(`/api/tasks/${taskId}/lines/${l.id}`, 'DELETE').then(invalidate)}
            onUpdate={(patch) => updateLine.mutate({ lineId: l.id, patch })}
          />
        ))}
        {lines.length === 0 && <Card className="py-10 text-center text-sm text-muted">暂无句子</Card>}
      </div>

      {showAnalyze && (
        <AnalyzeDialog
          taskId={taskId}
          lines={lines}
          selectedIds={[...selected]}
          onApplied={() => {
            setShowAnalyze(false)
            invalidate()
            setNotice('AI 建议已应用，句子已重置为待合成')
          }}
        />
      )}

      {showPronunciation && <PronunciationDialog taskId={taskId} onClosed={() => { setShowPronunciation(false); invalidate() }} />}

      <PlayerBar />
      </div>
    </div>
  )
}

function RoleCard({
  role, voices, onSave,
}: {
  role: { id: string; name: string; color: string; voice_id: string; params: string | object }
  voices: { id: string; name: string }[]
  onSave: (patch: Record<string, unknown>) => void
}) {
  let info: { gender?: string; style?: string } = {}
  try {
    info = typeof role.params === 'string' ? JSON.parse(role.params || '{}') : role.params ?? {}
  } catch {
    info = {}
  }
  return (
    <Card className="space-y-2 py-3">
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: role.color }} />
        <span className="font-medium">{role.name}</span>
        {info.gender && <Badge>{info.gender}</Badge>}
      </div>
      {info.style && <p className="text-xs text-muted">{info.style}</p>}
      <Select
        size="sm"
        className="w-full"
        placeholder="绑定音色…"
        value={role.voice_id}
        onChange={(v) => onSave({ voice_id: v })}
        options={voices.map((v) => ({ value: v.id, label: v.name }))}
      />
    </Card>
  )
}

interface PronRule { id: string; find: string; replace: string }

function PronunciationDialog({ taskId, onClosed }: { taskId: string; onClosed: () => void }) {
  const [rules, setRules] = useState<{ global: PronRule[]; task: PronRule[] }>({ global: [], task: [] })
  const [find, setFind] = useState('')
  const [replace, setReplace] = useState('')
  const [error, setError] = useState('')

  const load = async () => setRules(await apiGet(`/api/pronunciations?task_id=${taskId}`))
  useEffect(() => {
    load().catch((e) => setError(String(e)))
  }, [])

  const add = useMutation({
    mutationFn: () => apiSend('/api/pronunciations', 'POST', { scope: 'task', task_id: taskId, find, replace }),
    onSuccess: () => {
      setFind('')
      setReplace('')
      load()
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  return (
    <Modal title="发音规则（本任务）" onClose={onClosed}>
      <p className="mb-3 text-xs text-muted">
        合成前自动替换（如多音字、人名读法），只影响送入引擎的文本、不改动原稿。全局规则在设置页维护，任务级优先于全局。
      </p>
      {rules.task.length > 0 && (
        <div className="mb-3 space-y-1">
          {rules.task.map((r) => (
            <div key={r.id} className="flex items-center gap-2 rounded-lg border border-border p-2 text-sm">
              <span className="font-medium">{r.find}</span>
              <span className="text-muted">→</span>
              <span className="flex-1 text-primary">{r.replace || '（删除）'}</span>
              <button
                className="text-muted hover:text-danger"
                onClick={() => apiSend(`/api/pronunciations/${r.id}`, 'DELETE').then(load)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <TextInput placeholder="原文（如：长城）" value={find} onChange={(e) => setFind(e.target.value)} />
        <TextInput placeholder="替换为（如：cháng chéng）" value={replace} onChange={(e) => setReplace(e.target.value)} />
        <Button className="shrink-0" disabled={!find.trim()} loading={add.isPending} onClick={() => add.mutate()}>添加</Button>
      </div>
      {rules.global.length > 0 && (
        <div className="mt-3 text-xs text-muted">
          全局规则（{rules.global.length} 条）同样生效：{rules.global.slice(0, 3).map((r) => `${r.find}→${r.replace}`).join('、')}
          {rules.global.length > 3 ? ' …' : ''}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      <div className="mt-4 flex justify-end">
        <Button variant="ghost" onClick={onClosed}>完成</Button>
      </div>
    </Modal>
  )
}

interface Suggestion {
  line_id: string
  emotion: string
  speed: number
  gap_after_ms: number
}

function AnalyzeDialog({
  taskId, lines, selectedIds, onApplied,
}: {
  taskId: string
  lines: LineRow[]
  selectedIds: string[]
  onApplied: () => void
}) {
  const [scope, setScope] = useState<'all' | 'selected'>(selectedIds.length > 0 ? 'selected' : 'all')
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')
  const lineById = new Map(lines.map((l) => [l.id, l]))

  const run = useMutation({
    mutationFn: () =>
      apiSend<{ suggestions: Suggestion[] }>(`/api/llm/tasks/${taskId}/analyze`, 'POST', {
        line_ids: scope === 'selected' ? selectedIds : undefined,
      }),
    onSuccess: (r) => {
      setSuggestions(r.suggestions)
      setChecked(new Set(r.suggestions.map((s) => s.line_id)))
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  const apply = useMutation({
    mutationFn: () =>
      apiSend(`/api/llm/tasks/${taskId}/apply-analysis`, 'POST', {
        items: suggestions!.filter((s) => checked.has(s.line_id)).map((s) => ({ ...s, line_id: s.line_id })),
      }),
    onSuccess: onApplied,
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  return (
    <Modal title="AI 语境分析" onClose={() => onApplied()}>
      {!suggestions ? (
        <div className="space-y-4">
          <p className="text-sm text-muted">LLM 将通读全文，为每句建议：情绪、语速、句后停顿。分析后可勾选应用，应用后句子重置为待合成。</p>
          <div className="flex gap-2 text-sm">
            <label className={`flex cursor-pointer items-center gap-2 rounded-lg border p-2.5 ${scope === 'all' ? 'border-primary' : 'border-border'}`}>
              <input type="radio" checked={scope === 'all'} onChange={() => setScope('all')} /> 全部句子（{lines.length}）
            </label>
            <label className={`flex cursor-pointer items-center gap-2 rounded-lg border p-2.5 ${scope === 'selected' ? 'border-primary' : 'border-border'}`}>
              <input type="radio" checked={scope === 'selected'} onChange={() => setScope('selected')} disabled={selectedIds.length === 0} />
              选中句子（{selectedIds.length}）
            </label>
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
          <div className="flex justify-end">
            <Button loading={run.isPending} onClick={() => run.mutate()}>
              <Sparkles size={14} /> 开始分析
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
            {suggestions.map((s) => {
              const line = lineById.get(s.line_id)
              return (
                <label key={s.line_id} className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-border p-2 text-xs hover:bg-surface-2">
                  <input
                    type="checkbox"
                    checked={checked.has(s.line_id)}
                    onChange={() => {
                      const c = new Set(checked)
                      if (c.has(s.line_id)) c.delete(s.line_id)
                      else c.add(s.line_id)
                      setChecked(c)
                    }}
                  />
                  <span className="w-8 shrink-0 text-muted">#{lines.findIndex((l) => l.id === s.line_id) + 1}</span>
                  <span className="min-w-0 flex-1 truncate">{line?.text}</span>
                  <Badge tone="primary">{s.emotion}</Badge>
                  <span>语速 {s.speed.toFixed(2)}x</span>
                  <span>停顿 {s.gap_after_ms}ms</span>
                </label>
              )
            })}
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setSuggestions(null)}>重新分析</Button>
            <Button loading={apply.isPending} disabled={checked.size === 0} onClick={() => apply.mutate()}>
              应用勾选的 {checked.size} 条建议
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function LineCard({
  line, index, isFirst, isLast, expanded, selected, synthRunning, synthDisabled, providerCaps, roleInfo,
  onToggleSelect, onExpand, onPlay, onSynth, onMove, onDelete, onUpdate,
}: {
  line: LineRow
  index: number
  isFirst: boolean
  isLast: boolean
  expanded: boolean
  selected: boolean
  synthRunning: boolean
  synthDisabled: boolean
  providerCaps?: { pitch: boolean; emotion: boolean; instruct: boolean }
  roleInfo?: { name: string; color: string }
  onToggleSelect: () => void
  onExpand: () => void
  onPlay: () => void
  onSynth: () => void
  onMove: (dir: 'up' | 'down') => void
  onDelete: () => void
  onUpdate: (patch: Record<string, unknown>) => void
}) {
  const [text, setText] = useState(line.text)
  const [speed, setSpeed] = useState(line.speed ?? 1.0)
  const [pitch, setPitch] = useState(line.pitch ?? 0)
  const [volume, setVolume] = useState(line.volume ?? 1.0)
  const [gap, setGap] = useState(line.gap_after_ms ?? 300)
  const [emotion, setEmotion] = useState(line.emotion ?? '')
  const [instruct, setInstruct] = useState(line.instruct ?? '')
  useEffect(() => setText(line.text), [line.text])

  const dirty =
    text !== line.text || speed !== (line.speed ?? 1.0) || pitch !== (line.pitch ?? 0) ||
    volume !== (line.volume ?? 1.0) || gap !== (line.gap_after_ms ?? 300) || emotion !== (line.emotion ?? '') ||
    instruct !== (line.instruct ?? '')

  return (
    <Card className={`space-y-2 py-3 ${selected ? 'border-primary/60' : ''}`}>
      <div className="flex items-start gap-2.5">
        <input type="checkbox" className="mt-1.5" checked={selected} onChange={onToggleSelect} />
        <span className="mt-0.5 w-7 shrink-0 text-right font-mono text-xs text-muted">{index + 1}</span>
        {roleInfo && (
          <span className="mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium text-white" style={{ background: roleInfo.color }}>
            {roleInfo.name}
          </span>
        )}
        <span className="mt-1 shrink-0">
          {line.status === 'done' && <CircleCheck size={16} className="text-ok" />}
          {line.status === 'pending' && <CircleDashed size={16} className="text-muted" />}
          {line.status === 'synthesizing' && <Loader2 size={16} className="animate-spin text-primary" />}
          {line.status === 'failed' && (
            <span title={line.error}>
              <TriangleAlert size={16} className="text-danger" />
            </span>
          )}
        </span>
        <textarea
          className="min-h-9 flex-1 resize-y rounded-md border border-transparent bg-transparent px-1.5 py-1 text-sm leading-relaxed outline-none transition hover:border-border focus:border-primary focus:bg-surface"
          value={text}
          rows={Math.min(4, Math.ceil(text.length / 46))}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => text.trim() && text !== line.text && onUpdate({ text: text.trim() })}
        />
        <div className="flex shrink-0 items-center gap-0.5">
          {line.duration_ms != null && line.status === 'done' && (
            <span className="mr-1 text-xs text-muted">{(line.duration_ms / 1000).toFixed(1)}s</span>
          )}
          {line.status === 'done' && (
            <button title="试听" onClick={onPlay} className="rounded-md p-1.5 text-primary hover:bg-surface-2">
              <Play size={15} />
            </button>
          )}
          <button
            title={synthRunning ? '生成中…' : line.status === 'done' ? '重新合成' : '合成'}
            onClick={onSynth}
            disabled={synthDisabled || line.status === 'synthesizing'}
            className="rounded-md p-1.5 text-primary hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {synthRunning ? <Loader2 size={15} className="animate-spin" /> : <AudioLines size={15} />}
          </button>
          <button
            title="语气 / 停顿参数"
            onClick={onExpand}
            className={`rounded-md p-1.5 transition hover:bg-surface-2 ${expanded ? 'text-primary' : 'text-muted hover:text-text'}`}
          >
            <Settings2 size={15} />
          </button>
          <div className="flex flex-col">
            <button title="上移" disabled={isFirst} onClick={() => onMove('up')} className="rounded p-0.5 text-muted hover:text-text disabled:opacity-25">
              <ChevronUp size={13} />
            </button>
            <button title="下移" disabled={isLast} onClick={() => onMove('down')} className="rounded p-0.5 text-muted hover:text-text disabled:opacity-25">
              <ChevronDown size={13} />
            </button>
          </div>
          <button title="删除" onClick={onDelete} className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-danger">
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      {/* 状态/覆盖标记 */}
      <div className="flex flex-wrap items-center gap-1.5 pl-[74px] text-xs text-muted">
          {line.status === 'failed' && (
            <span className="text-danger" title={line.error}>
              <TriangleAlert size={16} className="inline align-[-2px]" /> {line.error}
            </span>
          )}
        {line.speed != null && <Badge>语速 {line.speed.toFixed(2)}x</Badge>}
        {line.pitch != null && line.pitch !== 0 && <Badge>音调 {line.pitch}Hz</Badge>}
        {line.volume != null && line.volume !== 1.0 && <Badge>音量 {Math.round(line.volume * 100)}%</Badge>}
        {line.gap_after_ms != null && <Badge>停顿 {line.gap_after_ms}ms</Badge>}
        {line.emotion && <Badge tone="primary">{line.emotion}</Badge>}
        {dirty && <span className="text-warn">参数未保存</span>}
      </div>

      {expanded && (
        <div className="ml-[74px] grid gap-x-6 gap-y-3 rounded-lg border border-border bg-surface-2/50 p-3 sm:grid-cols-2">
          <Slider label="语速覆盖" value={speed} min={0.5} max={2} step={0.05} onChange={setSpeed} format={(v) => `${v.toFixed(2)}x`} />
          <Slider label="音调覆盖" value={pitch} min={-100} max={100} step={5} onChange={setPitch} format={(v) => (v === 0 ? '不变' : `${v > 0 ? '+' : ''}${v}Hz`)} disabled={!providerCaps?.pitch} />
          <Slider label="音量覆盖" value={volume} min={0.1} max={2} step={0.05} onChange={setVolume} format={(v) => `${Math.round(v * 100)}%`} />
          <Slider label="本句后停顿" value={gap} min={0} max={2000} step={50} onChange={setGap} format={(v) => `${v}ms`} />
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="mb-1 block text-xs text-muted">情绪（引擎支持时生效）</label>
              <Select
                className="w-full"
                value={emotion}
                onChange={setEmotion}
                options={EMOTIONS.map((e) => ({ value: e, label: e || '默认' }))}
              />
            </div>
            <Button
              variant="ghost"
              className="text-xs"
              title="清除全部覆盖，恢复任务默认"
              onClick={() => {
                setSpeed(1.0); setPitch(0); setVolume(1.0); setGap(300); setEmotion(''); setInstruct('')
              }}
            >
              恢复默认
            </Button>
          </div>
          {providerCaps?.instruct && (
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs text-muted">语气描述（仅对支持 instruct 的引擎生效，如「疲惫地低声说」）</label>
              <TextInput value={instruct} onChange={(e) => setInstruct(e.target.value)} placeholder="自由描述这句台词的语气…" />
            </div>
          )}
          <div className="flex items-end justify-end gap-2">
            <Button className="text-xs" disabled={!dirty} onClick={() => onUpdate({ speed, pitch, volume, gap_after_ms: gap, emotion, instruct })}>
              保存参数并重置合成
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}
