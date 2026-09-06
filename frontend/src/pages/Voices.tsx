import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AudioLines, Download, Mic, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import { apiGet, apiSend, apiUpload } from '../api/client'
import type { BuiltinVoice, ProviderInfo } from '../api/types'
import { Badge, Button, Card, EmptyState, FileDrop, Modal, Select, TextInput } from '../components/ui'

interface VoiceRecord {
  id: string
  name: string
  description: string
  gender: string
  tags: string[]
  source: string
  ref_audio_path: string
  prompt_text: string
  prompt_lang: string
  sample_audio_path: string
  sample_url?: string
  sample_error?: string
  clone_error?: string
  provider_assets: Record<string, Record<string, string>>
}

interface VoicesResponse {
  voices: VoiceRecord[]
  provider_states: Record<string, Record<string, string>>
}

const CLOUD_CLONE_PROVIDERS = ['siliconflow', 'minimax', 'elevenlabs']
const BUILTIN_PROVIDERS = ['edge', 'siliconflow', 'minimax', 'elevenlabs', 'openai_compat']
// 复刻流程可选的引擎：本地零样本优先（保存即可合成试听），云端克隆引擎其后（保存即克隆）
const REF_AUDIO_PROVIDERS = ['indextts', 'gptsovits', 'cosyvoice', 'siliconflow', 'minimax', 'elevenlabs']

export default function Voices() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['voices'],
    queryFn: () => apiGet<VoicesResponse>('/api/voices'),
  })
  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })
  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id

  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<VoiceRecord | null>(null)
  const [cloneTarget, setCloneTarget] = useState<VoiceRecord | null>(null)
  const [samplingId, setSamplingId] = useState('')
  const [notice, setNotice] = useState('')

  const cloneMutation = useMutation({
    mutationFn: ({ voiceId, providerId }: { voiceId: string; providerId: string }) =>
      apiSend<VoiceRecord>(`/api/voices/${voiceId}/clone/${providerId}`, 'POST'),
    onSuccess: (v) => {
      setCloneTarget(null)
      setNotice(
        v.sample_error
          ? `已克隆「${v.name}」，但试听样本生成失败：${v.sample_error}；可点击音色卡上的「生成试听样本」重试`
          : `已克隆「${v.name}」，试听样本已更新`,
      )
      queryClient.invalidateQueries({ queryKey: ['voices'] })
    },
    onError: (e) => setNotice(e instanceof Error ? e.message : String(e)),
  })

  // 自动选一个可用引擎生成/重生成试听样本
  const makeSample = useMutation({
    mutationFn: (voiceId: string) => {
      setSamplingId(voiceId)
      return apiSend<VoiceRecord>(`/api/voices/${voiceId}/sample`, 'POST')
    },
    onSuccess: () => {
      setSamplingId('')
      queryClient.invalidateQueries({ queryKey: ['voices'] })
    },
    onError: (e) => {
      setSamplingId('')
      setNotice(e instanceof Error ? e.message : String(e))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (voiceId: string) => apiSend(`/api/voices/${voiceId}`, 'DELETE'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['voices'] }),
  })

  if (isLoading) return <div className="py-20 text-center text-sm text-muted">加载音色库…</div>

  const voices = data?.voices ?? []
  const states = data?.provider_states ?? {}

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">音色库</h1>
          <p className="text-xs text-muted">上传一段 5~30 秒参考音频即可复刻音色；保存后可在所有配音任务中复用。</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus size={15} /> 新建音色
        </Button>
      </div>

      {notice && (
        <Card className="flex items-center justify-between border-primary/30 bg-primary/5 py-2.5">
          <span className="text-sm text-primary">{notice}</span>
          <Button variant="ghost" onClick={() => setNotice('')}>知道了</Button>
        </Card>
      )}

      {voices.length === 0 ? (
        <EmptyState
          icon={<Mic size={32} />}
          title="音色库还是空的"
          desc="点击「新建音色」上传参考音频复刻声音，或把 Edge TTS 等引擎的内置音色加入音色库统一管理。"
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {voices.map((v) => {
            const perStates = states[v.id] ?? {}
            const cloneTargets = CLOUD_CLONE_PROVIDERS.filter(
              (pid) => perStates[pid] === 'needs_clone' && providers.find((p) => p.id === pid)?.configured,
            )
            return (
              <Card key={v.id} className="flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2 font-medium">
                      {v.name}
                      <Badge tone={v.source === 'builtin' ? 'muted' : 'primary'}>
                        {v.source === 'builtin' ? '内置' : '复刻'}
                      </Badge>
                      {v.gender && <Badge>{v.gender}</Badge>}
                    </div>
                    {v.description && <p className="mt-1 line-clamp-2 text-xs text-muted">{v.description}</p>}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      title="编辑"
                      onClick={() => setEditing(v)}
                      className="rounded-md p-1.5 text-muted transition hover:bg-surface-2 hover:text-text"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      title="删除"
                      onClick={() => {
                        if (confirm(`确定删除音色「${v.name}」？`)) deleteMutation.mutate(v.id)
                      }}
                      className="rounded-md p-1.5 text-muted transition hover:bg-surface-2 hover:text-danger"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {v.sample_url ? (
                  <audio controls src={v.sample_url} className="h-8 w-full" />
                ) : (
                  <Button
                    variant="outline"
                    className="w-full text-xs"
                    loading={samplingId === v.id}
                    disabled={samplingId !== ''}
                    onClick={() => makeSample.mutate(v.id)}
                  >
                    <AudioLines size={13} /> 生成试听样本
                  </Button>
                )}

                <div className="flex flex-wrap gap-1.5">
                  {providers.map((p) => {
                    const st = perStates[p.id]
                    if (st === 'unsupported') return null
                    if (st === 'ready') return <Badge key={p.id} tone="ok">{p.name} ✓</Badge>
                    if (st === 'needs_clone')
                      return (
                        <button
                          key={p.id}
                          disabled={!p.configured}
                          title={p.configured ? `克隆到 ${p.name}` : `${p.name} 未配置`}
                          onClick={() => setCloneTarget(v)}
                          className="inline-flex items-center rounded-full bg-warn/10 px-2 py-0.5 text-xs font-medium text-warn transition hover:bg-warn/20 disabled:opacity-40"
                        >
                          克隆到 {p.name}
                        </button>
                      )
                    return null
                  })}
                </div>

                {(cloneTargets.length > 0) && (
                  <div className="mt-auto flex gap-2 border-t border-border pt-2.5">
                    <Button
                      variant="outline"
                      className="flex-1 text-xs"
                      loading={cloneMutation.isPending}
                      onClick={() => setCloneTarget(v)}
                    >
                      <Upload size={13} /> 克隆到云端引擎
                    </Button>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {showCreate && <CreateVoiceDialog onClose={() => setShowCreate(false)} onNotice={setNotice} />}
      {editing && <EditVoiceDialog voice={editing} onClose={() => setEditing(null)} />}
      {cloneTarget && (
        <CloneDialog
          voice={cloneTarget}
          providers={providers.filter((p) => CLOUD_CLONE_PROVIDERS.includes(p.id))}
          states={states[cloneTarget.id] ?? {}}
          loading={cloneMutation.isPending}
          error={cloneMutation.error instanceof Error ? cloneMutation.error.message : ''}
          onClone={(pid) => cloneMutation.mutate({ voiceId: cloneTarget.id, providerId: pid })}
          onClose={() => setCloneTarget(null)}
        />
      )}
    </div>
  )
}

function providerVoiceListKey(pid: string) {
  return ['builtin-voices', pid] as const
}

function CreateVoiceDialog({ onClose, onNotice }: { onClose: () => void; onNotice: (msg: string) => void }) {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<'clone' | 'builtin'>('clone')
  const [name, setName] = useState('')
  const [gender, setGender] = useState('女')
  const [description, setDescription] = useState('')
  const [promptText, setPromptText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [providerId, setProviderId] = useState('edge')
  const [cloneProviderId, setCloneProviderId] = useState('')
  const [builtinName, setBuiltinName] = useState('')
  const [error, setError] = useState('')

  const voicesQuery = useQuery({
    queryKey: providerVoiceListKey(providerId),
    enabled: tab === 'builtin',
    queryFn: () => apiGet<BuiltinVoice[]>(`/api/providers/${providerId}/voices`),
  })
  const builtinVoices = useMemo(() => (voicesQuery.data ?? []).slice(0, 500), [voicesQuery.data])
  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })
  const cloneProviders = useMemo(
    () =>
      REF_AUDIO_PROVIDERS.map((id) => providers.find((p) => p.id === id)).filter(
        (p): p is ProviderInfo => !!p && p.configured,
      ),
    [providers],
  )
  useEffect(() => {
    if (!cloneProviderId && cloneProviders.length > 0) setCloneProviderId(cloneProviders[0].id)
  }, [cloneProviderId, cloneProviders])

  const createMutation = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      form.set('name', name)
      form.set('gender', gender)
      form.set('description', description)
      form.set('prompt_text', promptText)
      if (tab === 'clone' && file) {
        form.set('ref_audio', file)
        form.set('provider_id', cloneProviderId)
      }
      if (tab === 'builtin') {
        form.set('provider_id', providerId)
        form.set('builtin_voice_name', builtinName)
      }
      return apiUpload<VoiceRecord>('/api/voices', form)
    },
    onSuccess: (v) => {
      queryClient.invalidateQueries({ queryKey: ['voices'] })
      const errs: string[] = []
      if (v.clone_error) errs.push(`克隆失败：${v.clone_error}`)
      if (v.sample_error) errs.push(`试听样本生成失败：${v.sample_error}（可在音色卡上点「生成试听样本」重试）`)
      onNotice(errs.length > 0 ? errs.join('；') : v.sample_url ? '音色已创建，试听样本已生成' : '音色已创建')
      onClose()
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })

  const submit = () => {
    setError('')
    if (!name.trim()) return setError('请填写音色名称')
    if (tab === 'clone' && !cloneProviderId) return setError('请先选择 AI 模型（引擎）；若列表为空请先到设置页配置')
    if (tab === 'clone' && !file) return setError('请选择参考音频文件（5~30 秒 wav/mp3）')
    if (tab === 'builtin' && !builtinName) return setError('请选择要加入的内置音色')
    createMutation.mutate()
  }

  return (
    <Modal title="新建音色" onClose={onClose}>
      <div className="mb-4 flex gap-1 rounded-lg bg-surface-2 p-1 text-sm">
        <button
          className={`flex-1 rounded-md px-3 py-1.5 ${tab === 'clone' ? 'bg-surface font-medium shadow-sm' : 'text-muted'}`}
          onClick={() => setTab('clone')}
        >
          上传参考音频复刻
        </button>
        <button
          className={`flex-1 rounded-md px-3 py-1.5 ${tab === 'builtin' ? 'bg-surface font-medium shadow-sm' : 'text-muted'}`}
          onClick={() => setTab('builtin')}
        >
          加入内置音色
        </button>
      </div>

      {tab === 'clone' ? (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted">AI 模型（引擎）</label>
            <Select
              className="w-full"
              placeholder="请选择引擎"
              value={cloneProviderId}
              onChange={setCloneProviderId}
              options={cloneProviders.map((p) => ({ value: p.id, label: p.name }))}
            />
            <p className="mt-1 text-xs text-muted">
              云端引擎（SiliconFlow / MiniMax / ElevenLabs）保存时自动用参考音频克隆；本地零样本引擎保存后直接合成试听样本。
            </p>
          </div>
          <FileDrop
            accept=".wav,.mp3,.m4a,.ogg,.flac"
            onFile={(f) => {
              if (!/\.(wav|mp3|m4a|ogg|flac)$/i.test(f.name)) return setError('仅支持音频文件（wav / mp3 / m4a / ogg / flac）')
              setError('')
              setFile(f)
              if (!name.trim()) setName(f.name.replace(/\.[^.]+$/, ''))
            }}
            className="rounded-xl border-2 border-dashed border-border py-8 text-center hover:border-primary/50 hover:bg-surface-2"
          >
            <Upload size={22} className="mx-auto mb-2 text-muted" />
            {file ? (
              <div className="text-sm">
                已选择：<span className="font-medium">{file.name}</span>
                <span className="text-muted">（{(file.size / 1024 / 1024).toFixed(1)}MB）</span>
              </div>
            ) : (
              <div className="text-sm text-muted">点击选择或拖拽参考音频到此处（wav / mp3，建议 5~30 秒、清晰人声）</div>
            )}
          </FileDrop>
          <div>
            <label className="mb-1 block text-xs text-muted">
              参考文本（选填；保存后将用这段文本合成卡上的试听样本；GPT-SoVITS 建议填写音频里说的话）
            </label>
            <TextInput value={promptText} onChange={(e) => setPromptText(e.target.value)} placeholder="例如：今天天气真不错，我们出去走走吧。" />
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted">引擎</label>
            <Select
              className="w-full"
              value={providerId}
              onChange={(v) => {
                setProviderId(v)
                setBuiltinName('')
              }}
              options={BUILTIN_PROVIDERS.map((pid) => ({ value: pid, label: pid }))}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">音色</label>
            <Select
              searchable
              className="w-full"
              placeholder={voicesQuery.isLoading ? '加载中…' : '请选择音色'}
              value={builtinName}
              onChange={(v) => {
                setBuiltinName(v)
                const voice = builtinVoices.find((x) => x.name === v)
                if (voice && !name.trim()) setName(voice.display_name || voice.name)
              }}
              options={builtinVoices.map((v) => ({
                value: v.name,
                label: `${v.display_name || v.name}${v.gender ? ` · ${v.gender}` : ''}`,
              }))}
            />
          </div>
        </div>
      )}

      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_120px]">
        <div>
          <label className="mb-1 block text-xs text-muted">音色名称</label>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="如：我的主持音色" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted">性别</label>
          <Select
            className="w-full"
            value={gender}
            onChange={setGender}
            options={[
              { value: '女', label: '女' },
              { value: '男', label: '男' },
              { value: '', label: '未指定' },
            ]}
          />
        </div>
      </div>
      <div className="mt-3">
        <label className="mb-1 block text-xs text-muted">描述（选填）</label>
        <TextInput value={description} onChange={(e) => setDescription(e.target.value)} placeholder="音色特点、适用场景等" />
      </div>

      {error && <p className="mt-3 text-xs text-danger">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button loading={createMutation.isPending} onClick={submit}>保存音色</Button>
      </div>
    </Modal>
  )
}

function EditVoiceDialog({ voice, onClose }: { voice: VoiceRecord; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(voice.name)
  const [gender, setGender] = useState(voice.gender || '')
  const [description, setDescription] = useState(voice.description)
  const [error, setError] = useState('')
  const save = useMutation({
    mutationFn: () => apiSend(`/api/voices/${voice.id}`, 'PUT', { name, gender, description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['voices'] })
      onClose()
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  })
  return (
    <Modal title="编辑音色" onClose={onClose}>
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
          <div>
            <label className="mb-1 block text-xs text-muted">名称</label>
            <TextInput value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">性别</label>
            <Select
              className="w-full"
              value={gender}
              onChange={setGender}
              options={[
                { value: '女', label: '女' },
                { value: '男', label: '男' },
                { value: '', label: '未指定' },
              ]}
            />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted">描述</label>
          <TextInput value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        {error && <p className="text-xs text-danger">{error}</p>}
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button loading={save.isPending} onClick={() => save.mutate()}>保存</Button>
      </div>
    </Modal>
  )
}

function CloneDialog({
  voice, providers, states, loading, error, onClone, onClose,
}: {
  voice: VoiceRecord
  providers: ProviderInfo[]
  states: Record<string, string>
  loading: boolean
  error: string
  onClone: (providerId: string) => void
  onClose: () => void
}) {
  const [selected, setSelected] = useState(providers.find((p) => states[p.id] === 'needs_clone')?.id ?? '')
  return (
    <Modal title={`克隆「${voice.name}」到云端引擎`} onClose={onClose}>
      <p className="mb-3 text-xs text-muted">
        将参考音频上传到引擎完成即时克隆（通常数秒）。克隆一次后可长期复用；同一音色可克隆到多个引擎。
      </p>
      <div className="space-y-2">
        {providers.map((p) => (
          <label
            key={p.id}
            className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm transition ${
              selected === p.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-surface-2'
            } ${states[p.id] === 'ready' ? 'opacity-60' : ''}`}
          >
            <input
              type="radio"
              name="clone-provider"
              checked={selected === p.id}
              disabled={!p.configured || states[p.id] === 'ready'}
              onChange={() => setSelected(p.id)}
            />
            <div className="flex-1">
              <div className="font-medium">{p.name}</div>
              <div className="text-xs text-muted">{p.description}</div>
            </div>
            {states[p.id] === 'ready' && <Badge tone="ok">已克隆</Badge>}
            {!p.configured && <Badge tone="warn">未配置</Badge>}
          </label>
        ))}
      </div>
      {error && <p className="mt-3 text-xs text-danger">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button loading={loading} disabled={!selected} onClick={() => onClone(selected)}>
          <Download size={14} /> 开始克隆
        </Button>
      </div>
    </Modal>
  )
}

