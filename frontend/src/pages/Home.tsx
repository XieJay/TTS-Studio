import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardType, FileUp, ListMusic, Mic, Pencil, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { apiGet, apiSend, apiUpload } from '../api/client'
import type { BuiltinVoice, ProviderInfo, SystemStatus } from '../api/types'
import { Badge, Button, Card, EmptyState, FileDrop, Modal, Select, TextInput } from '../components/ui'

interface TaskRow {
  id: string
  title: string
  mode: string
  voice_id: string
  line_count: number
  done_count: number
  updated_at: string
}

export default function Home() {
  const { data: tasks = [], isLoading } = useQuery({ queryKey: ['tasks'], queryFn: () => apiGet<TaskRow[]>('/api/tasks') })
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [showAdapt, setShowAdapt] = useState(false)
  const [renaming, setRenaming] = useState<TaskRow | null>(null)
  const navigate = useNavigate()

  const del = useMutation({
    mutationFn: (id: string) => apiSend(`/api/tasks/${id}`, 'DELETE'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => apiSend(`/api/tasks/${id}`, 'PUT', { title }),
    onSuccess: () => {
      setRenaming(null)
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  return (
    <div className="space-y-6">
      <Card className="flex flex-col gap-3 bg-gradient-to-br from-primary/5 to-transparent sm:flex-row sm:items-center">
        <div className="flex-1">
          <h1 className="text-xl font-semibold">配音任务</h1>
          <p className="mt-1 text-sm text-muted">上传主持稿或粘贴文本 → 选定音色 → 批量合成 → 试听微调 → 导出</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowAdapt(true)}>
            <Sparkles size={15} /> AI 改编剧本
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus size={16} /> 新建配音任务
          </Button>
        </div>
      </Card>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-muted">加载中…</div>
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={<ListMusic size={32} />}
          title="还没有配音任务"
          desc="点击「新建配音任务」上传主持稿（txt / md / docx）或直接粘贴文本，系统会自动分句，然后为整篇稿件指定音色批量合成。"
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {tasks.map((t) => {
            const pct = t.line_count > 0 ? Math.round((t.done_count / t.line_count) * 100) : 0
            return (
              <Card key={t.id} className="cursor-pointer transition hover:border-primary/50" >
                <div onClick={() => navigate(`/studio/${t.id}`)}>
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 font-medium">{t.title}</div>
                    <div className="ml-2 flex shrink-0 items-center gap-0.5">
                      <button
                        title="重命名"
                        onClick={(e) => {
                          e.stopPropagation()
                          setRenaming(t)
                        }}
                        className="rounded-md p-1 text-muted transition hover:bg-surface-2 hover:text-text"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        title="删除任务"
                        onClick={(e) => {
                          e.stopPropagation()
                          if (confirm(`确定删除任务「${t.title}」？已合成的音频将一并删除。`)) del.mutate(t.id)
                        }}
                        className="rounded-md p-1 text-muted transition hover:bg-surface-2 hover:text-danger"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-xs text-muted">
                    <Badge tone={t.mode === 'dialogue' ? 'primary' : 'muted'}>
                      {t.mode === 'dialogue' ? '多角色' : '单音色'}
                    </Badge>
                    <span>{t.line_count} 句</span>
                    <span>· {t.updated_at.slice(5, 16)}</span>
                  </div>
                  <div className="mt-3">
                    <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
                    </div>
                    <div className="mt-1 text-xs text-muted">{t.done_count}/{t.line_count} 已合成</div>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {showCreate && <CreateWizard onClose={() => setShowCreate(false)} />}
      {renaming && (
        <RenameDialog
          initial={renaming.title}
          loading={rename.isPending}
          error={rename.error instanceof Error ? rename.error.message : ''}
          onSave={(title) => rename.mutate({ id: renaming.id, title })}
          onClose={() => setRenaming(null)}
        />
      )}
      {showAdapt && (
        <AdaptDialog
          onClose={() => setShowAdapt(false)}
          onCreated={(id) => {
            setShowAdapt(false)
            queryClient.invalidateQueries({ queryKey: ['tasks'] })
            navigate(`/studio/${id}`)
          }}
        />
      )}
    </div>
  )
}

interface AdaptDraft {
  title: string
  cast: { name: string; gender: string; style: string }[]
  lines: { role: string; text: string }[]
}

function RenameDialog({
  initial, loading, error, onSave, onClose,
}: {
  initial: string
  loading: boolean
  error: string
  onSave: (title: string) => void
  onClose: () => void
}) {
  const [title, setTitle] = useState(initial)
  return (
    <Modal title="重命名任务" onClose={onClose}>
      <TextInput
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && title.trim() && title.trim() !== initial) onSave(title.trim())
        }}
      />
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button loading={loading} disabled={!title.trim() || title.trim() === initial} onClick={() => onSave(title.trim())}>
          保存
        </Button>
      </div>
    </Modal>
  )
}

function AdaptDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (taskId: string) => void }) {
  const [text, setText] = useState('')
  const [maxRoles, setMaxRoles] = useState(4)
  const [providerId, setProviderId] = useState('edge')
  const [draft, setDraft] = useState<AdaptDraft | null>(null)
  const [error, setError] = useState('')

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })
  const configured = providers.filter((p) => p.configured)

  const adapt = useMutation({
    mutationFn: () => apiSend<AdaptDraft>('/api/llm/adapt', 'POST', { text, max_roles: maxRoles }),
    onSuccess: setDraft,
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  const create = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      form.set('title', draft!.title || 'AI 改编剧本')
      form.set('mode', 'dialogue')
      form.set('provider_id', providerId)
      form.set('cast', JSON.stringify(draft!.cast))
      form.set('text', draft!.lines.map((l) => `${l.role}: ${l.text}`).join('\n'))
      return apiUpload<{ task: { id: string } }>('/api/tasks', form)
    },
    onSuccess: (r) => onCreated(r.task.id),
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  return (
    <Modal title="AI 改编：小说 → 多角色对话剧本" onClose={onClose}>
      {!draft ? (
        <div className="space-y-3">
          <textarea
            className="min-h-48 w-full resize-y rounded-lg border border-border bg-surface p-3 text-sm outline-none focus:border-primary"
            placeholder="粘贴小说或文章原文（建议 ≤8000 字）…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <span className="text-xs text-muted">角色数上限</span>
              <Select
                size="sm"
                className="min-w-14"
                value={String(maxRoles)}
                onChange={(v) => setMaxRoles(Number(v))}
                options={[2, 3, 4, 5, 6].map((n) => ({ value: String(n), label: String(n) }))}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <span className="text-xs text-muted">合成引擎</span>
              <Select
                size="sm"
                className="min-w-36"
                value={providerId}
                onChange={setProviderId}
                options={(configured.length > 0 ? configured : providers).map((p) => ({ value: p.id, label: p.name }))}
              />
            </label>
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
          <div className="flex justify-end">
            <Button loading={adapt.isPending} disabled={!text.trim()} onClick={() => adapt.mutate()}>
              <Sparkles size={14} /> 开始改编
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <div className="text-xs text-muted">剧本标题</div>
            <TextInput value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </div>
          <div>
            <div className="mb-1 text-xs text-muted">角色（{draft.cast.length} 个，创建后可在工作台绑定音色）</div>
            <div className="flex flex-wrap gap-1.5">
              {draft.cast.map((c) => (
                <Badge key={c.name} tone="primary">
                  {c.name} · {c.gender}
                  {c.style ? ` · ${c.style}` : ''}
                </Badge>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs text-muted">台词（{draft.lines.length} 句，创建后可继续编辑）</div>
            <div className="max-h-52 space-y-1 overflow-y-auto rounded-lg border border-border p-2">
              {draft.lines.map((l, i) => (
                <div key={i} className="flex gap-2 text-xs">
                  <span className="w-6 shrink-0 text-right text-muted">{i + 1}</span>
                  <span className="shrink-0 font-medium text-primary">{l.role}</span>
                  <span className="text-muted">{l.text}</span>
                </div>
              ))}
            </div>
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => setDraft(null)}>重新改编</Button>
            <Button loading={create.isPending} onClick={() => create.mutate()}>创建多角色任务</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function CreateWizard({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [title, setTitle] = useState('')
  const [mode, setMode] = useState<'script' | 'dialogue'>('script')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [voiceId, setVoiceId] = useState('')
  const [providerId, setProviderId] = useState('edge')
  const [preview, setPreview] = useState<{ count: number; units: { text: string; role?: string }[] } | null>(null)
  const [error, setError] = useState('')

  const { data: voices = [] } = useQuery({
    queryKey: ['voices'],
    queryFn: () => apiGet<{ voices: { id: string; name: string; source: string; sample_url?: string }[] }>('/api/voices').then((r) => r.voices),
  })
  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })
  const configuredProviders = providers.filter((p) => p.configured)

  const previewMutation = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      form.set('mode', mode)
      if (file) form.set('file', file)
      else form.set('text', text)
      return apiUpload<{ count: number; units: { text: string; role?: string }[] }>(`/api/tasks/preview-split`, form)
    },
    onSuccess: (r) => {
      setPreview(r)
      setStep(2)
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      form.set('title', title || '未命名配音任务')
      form.set('mode', mode)
      form.set('voice_id', voiceId)
      form.set('provider_id', providerId)
      if (file) form.set('file', file)
      else form.set('text', text)
      return apiUpload<{ task: { id: string } }>(`/api/tasks`, form)
    },
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      navigate(`/studio/${r.task.id}`)
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  const canNext1 = (file !== null || text.trim().length > 0) && (mode === 'dialogue' || true)

  return (
    <Modal title="新建配音任务" onClose={onClose}>
      {/* 步骤条 */}
      <div className="mb-4 flex items-center gap-2 text-xs">
        {['内容来源', '音色与引擎', '分句确认'].map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${step > i ? 'bg-primary text-primary-fg' : 'bg-surface-2 text-muted'}`}>{i + 1}</span>
            <span className={step > i ? 'text-text' : 'text-muted'}>{s}</span>
            {i < 2 && <span className="text-muted">—</span>}
          </div>
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setMode('script')}
              className={`rounded-xl border p-3 text-left text-sm transition ${mode === 'script' ? 'border-primary bg-primary/5' : 'border-border hover:bg-surface-2'}`}
            >
              <Mic size={16} className="mb-1 text-primary" />
              <div className="font-medium">单音色稿件配音</div>
              <div className="text-xs text-muted">整篇稿子用一个音色（主持稿、文章朗读）</div>
            </button>
            <button
              onClick={() => setMode('dialogue')}
              className={`rounded-xl border p-3 text-left text-sm transition ${mode === 'dialogue' ? 'border-primary bg-primary/5' : 'border-border hover:bg-surface-2'}`}
            >
              <ClipboardType size={16} className="mb-1 text-primary" />
              <div className="font-medium">多角色对话配音</div>
              <div className="text-xs text-muted">「角色名: 台词」剧本，按角色分配音色</div>
            </button>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">任务标题</label>
            <TextInput value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如：年会主持稿配音" />
          </div>
          <FileDrop
            accept=".txt,.md,.docx"
            onFile={(f) => {
              if (!/\.(txt|md|docx)$/i.test(f.name)) return setError('仅支持 txt / md / docx 文件')
              setError('')
              setFile(f)
              if (!title.trim()) setTitle(f.name.replace(/\.[^.]+$/, ''))
            }}
            className="flex items-center gap-3 rounded-xl border-2 border-dashed border-border px-4 py-5 hover:border-primary/50 hover:bg-surface-2"
          >
            <FileUp size={20} className="text-muted" />
            <div className="text-sm">
              {file ? <><span className="font-medium">{file.name}</span>（{(file.size / 1024).toFixed(0)}KB）</> : '点击选择或拖拽稿件文件到此处（txt / md / docx）'}
            </div>
          </FileDrop>
          <div className="text-center text-xs text-muted">— 或 —</div>
          <textarea
            className="min-h-32 w-full resize-y rounded-lg border border-border bg-surface p-3 text-sm outline-none focus:border-primary"
            placeholder="直接粘贴稿件文本…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          {mode === 'script' ? (
            <>
              <div>
                <label className="mb-1 block text-xs text-muted">选择音色（创建后可随时更换）</label>
                <div className="max-h-44 space-y-1.5 overflow-y-auto pr-1">
                  {voices.length === 0 && <p className="text-xs text-warn">音色库为空，请先到「音色库」创建，或返回用多角色模式。</p>}
                  {voices.map((v) => (
                    <label
                      key={v.id}
                      className={`flex cursor-pointer items-center gap-3 rounded-lg border p-2.5 text-sm transition ${voiceId === v.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-surface-2'}`}
                    >
                      <input type="radio" name="voice" checked={voiceId === v.id} onChange={() => setVoiceId(v.id)} />
                      <span className="flex-1">{v.name}</span>
                      <Badge tone={v.source === 'builtin' ? 'muted' : 'primary'}>{v.source === 'builtin' ? '内置' : '复刻'}</Badge>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted">合成引擎</label>
                <Select
                  className="w-full"
                  value={providerId}
                  onChange={setProviderId}
                  options={
                    configuredProviders.length > 0
                      ? configuredProviders.map((p) => ({ value: p.id, label: p.name }))
                      : [{ value: 'edge', label: 'Edge TTS（免费）' }]
                  }
                />
                <p className="mt-1 text-xs text-muted">复刻音色需选择支持该音色的引擎（本地零样本或已克隆的云端引擎）。</p>
              </div>
            </>
          ) : (
            <div>
              <label className="mb-1 block text-xs text-muted">合成引擎（角色音色在工作台内绑定）</label>
              <Select
                className="w-full"
                value={providerId}
                onChange={setProviderId}
                options={configuredProviders.map((p) => ({ value: p.id, label: p.name }))}
              />
            </div>
          )}
        </div>
      )}

      {step === 3 && preview && (
        <div>
          <p className="mb-2 text-sm">
            已按标点与段落切分为 <span className="font-semibold text-primary">{preview.count}</span> 句（可在工作台手动调整）：
          </p>
          <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-border p-2">
            {preview.units.map((u, i) => (
              <div key={i} className="flex gap-2 text-xs">
                <span className="w-6 shrink-0 text-right text-muted">{i + 1}</span>
                {u.role && <span className="shrink-0 font-medium text-primary">{u.role}</span>}
                <span className="text-muted">{u.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <p className="mt-3 text-xs text-danger">{error}</p>}

      <div className="mt-5 flex justify-between">
        <Button variant="ghost" disabled={step === 1} onClick={() => setStep(step - 1)}>上一步</Button>
        {step < 3 ? (
          <Button
            disabled={step === 1 && !canNext1}
            loading={previewMutation.isPending}
            onClick={() => {
              setError('')
              if (step === 1) previewMutation.mutate()
              else if (step === 2) {
                if (mode === 'script' && !voiceId) return setError('请选择音色')
                setStep(3)
              }
            }}
          >
            {step === 1 ? '解析分句' : '下一步'}
          </Button>
        ) : (
          <Button loading={createMutation.isPending} onClick={() => createMutation.mutate()}>创建任务</Button>
        )}
      </div>
    </Modal>
  )
}

