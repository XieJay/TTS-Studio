import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Play, Plus, Trash2, Wand2 } from 'lucide-react'
import { apiAudio, apiGet } from '../api/client'
import type { BuiltinVoice, ProviderInfo } from '../api/types'
import { Badge, Button, Card, EmptyState, Select, Slider } from '../components/ui'

interface SynthResult {
  id: string
  providerName: string
  voiceName: string
  text: string
  speed: number
  url: string
  format: string
  createdAt: string
  comboTag?: string
}

interface Combo {
  id: string
  providerId: string
  providerName: string
  voiceName: string
  speed: number
  pitch: number
  volume: number
}

export default function Playground() {
  const { data: providers = [], isLoading } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })
  const [providerId, setProviderId] = useState('')
  const meta = useMemo(() => providers.find((p) => p.id === providerId), [providers, providerId])

  useEffect(() => {
    if (!providerId && providers.length > 0) {
      setProviderId(providers.find((p) => p.configured)?.id ?? providers[0].id)
    }
  }, [providers, providerId])

  const voicesQuery = useQuery({
    queryKey: ['voices', providerId],
    enabled: !!providerId && !!meta?.capabilities.builtin_voices,
    queryFn: () => apiGet<BuiltinVoice[]>(`/api/providers/${providerId}/voices`),
  })
  const [voiceName, setVoiceName] = useState('')
  const voices = useMemo(() => {
    // 中文音色置顶，其余按名称排序；搜索在下拉弹层内进行
    return [...(voicesQuery.data ?? [])]
      .sort((a, b) => {
        const az = a.language.startsWith('zh') ? 0 : 1
        const bz = b.language.startsWith('zh') ? 0 : 1
        return az - bz || a.name.localeCompare(b.name)
      })
      .slice(0, 500)
  }, [voicesQuery.data])

  const [text, setText] = useState('你好，欢迎收听本期节目，希望今天的声音能陪伴你。')
  const [speed, setSpeed] = useState(1.0)
  const [pitch, setPitch] = useState(0)
  const [volume, setVolume] = useState(1.0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [results, setResults] = useState<SynthResult[]>([])
  const [combos, setCombos] = useState<Combo[]>([])
  const [batchLoading, setBatchLoading] = useState(false)

  const addCombo = () => {
    if (!meta) return
    setCombos((cs) => [
      ...cs,
      {
        id: crypto.randomUUID(),
        providerId,
        providerName: meta.name,
        voiceName: voiceName || '默认音色',
        speed,
        pitch,
        volume,
      },
    ])
  }

  const synthOne = async (
    cfg: { providerId: string; voiceName: string; speed: number; pitch: number; volume: number },
    comboTag?: string,
  ) => {
    const { blob, format } = await apiAudio('/api/tts/preview', {
      provider_id: cfg.providerId,
      text: text.trim(),
      speed: cfg.speed,
      pitch: cfg.pitch === 0 ? null : cfg.pitch,
      volume: cfg.volume,
    })
    const url = URL.createObjectURL(blob)
    setResults((rs) => [
      {
        id: crypto.randomUUID(),
        providerName: providers.find((p) => p.id === cfg.providerId)?.name ?? cfg.providerId,
        voiceName: cfg.voiceName,
        text: text.trim(),
        speed: cfg.speed,
        url,
        format,
        createdAt: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        comboTag,
      },
      ...rs,
    ])
  }

  const synth = async () => {
    if (!providerId || !text.trim()) return
    setError('')
    setLoading(true)
    try {
      await synthOne({ providerId, voiceName: voiceName || '默认音色', speed, pitch, volume })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const runAllCombos = async () => {
    if (combos.length === 0 || !text.trim()) return
    setError('')
    setBatchLoading(true)
    try {
      for (let i = 0; i < combos.length; i++) {
        const c = combos[i]
        await synthOne(c, `A/B #${i + 1} ${c.voiceName}`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBatchLoading(false)
    }
  }

  const download = (r: SynthResult) => {
    const a = document.createElement('a')
    a.href = r.url
    a.download = `试炼_${r.createdAt.replace(/:/g, '')}_${r.voiceName}.${r.format}`
    a.click()
  }

  if (isLoading) return <div className="py-20 text-center text-sm text-muted">加载引擎中…</div>

  return (
    <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
      {/* 左侧：引擎与参数 */}
      <div className="space-y-4">
        <Card className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-muted">合成引擎</label>
            <Select
              className="w-full"
              value={providerId}
              onChange={(v) => {
                setProviderId(v)
                setVoiceName('')
              }}
              options={providers.map((p) => ({
                value: p.id,
                label: p.configured ? p.name : `${p.name}（未配置，去设置）`,
                disabled: !p.configured,
              }))}
            />
            {meta && <p className="mt-1.5 text-xs text-muted">{meta.description}</p>}
          </div>

          {meta?.capabilities.builtin_voices && (
            <div>
              <label className="mb-1 block text-xs text-muted">音色</label>
              <Select
                searchable
                className="w-full"
                placeholder={voicesQuery.isLoading ? '音色加载中…' : '默认音色（引擎推荐）'}
                value={voiceName}
                onChange={setVoiceName}
                options={[
                  { value: '', label: '默认音色（引擎推荐）' },
                  ...voices.map((v) => ({
                    value: v.name,
                    label: `${v.display_name || v.name}${v.gender ? ` · ${v.gender}` : ''}`,
                  })),
                ]}
              />
              <p className="mt-1.5 text-xs text-muted">
                共 {voicesQuery.data?.length ?? 0} 个音色，点击下拉框可搜索；默认用引擎推荐音色。
              </p>
            </div>
          )}

          <div className="space-y-3 border-t border-border pt-3">
            <Slider label="语速" value={speed} min={0.5} max={2} step={0.05} onChange={setSpeed} format={(v) => `${v.toFixed(2)}x`} />
            <Slider
              label="音调"
              value={pitch}
              min={-100}
              max={100}
              step={5}
              onChange={setPitch}
              format={(v) => (v === 0 ? '不变' : `${v > 0 ? '+' : ''}${v}Hz`)}
              disabled={!meta?.capabilities.pitch}
            />
            <Slider label="音量" value={volume} min={0.1} max={2} step={0.05} onChange={setVolume} format={(v) => `${Math.round(v * 100)}%`} />
            {!meta?.capabilities.pitch && (
              <p className="text-xs text-muted">当前引擎不支持原生音调调节，已禁用。</p>
            )}
          </div>

          {/* A/B 对比组合 */}
          <div className="space-y-2 border-t border-border pt-3">
            <div className="flex items-center gap-2">
              <Button variant="outline" className="flex-1 text-xs" onClick={addCombo} disabled={!meta?.configured}>
                <Plus size={13} /> 存为对比组合
              </Button>
              <Button
                variant="outline"
                className="flex-1 text-xs"
                loading={batchLoading}
                disabled={combos.length === 0 || !text.trim()}
                onClick={runAllCombos}
              >
                <Play size={13} /> 一键全部合成{combos.length > 0 ? `（${combos.length}）` : ''}
              </Button>
            </div>
            {combos.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {combos.map((c, i) => (
                  <span
                    key={c.id}
                    className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary"
                  >
                    #{i + 1} {c.voiceName} · {c.speed.toFixed(2)}x
                    <button
                      className="hover:text-danger"
                      onClick={() => setCombos((cs) => cs.filter((x) => x.id !== c.id))}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-muted">把多个「引擎+音色+参数」加入对比，一键全部合成后并排试听。</p>
          </div>
        </Card>
      </div>

      {/* 右侧：文本与结果 */}
      <div className="space-y-4">
        <Card className="space-y-3">
          <textarea
            className="min-h-28 w-full resize-y rounded-lg border border-border bg-surface p-3 text-sm outline-none transition placeholder:text-muted/60 focus:border-primary"
            placeholder="输入要合成的文本…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <Button onClick={synth} loading={loading} disabled={!text.trim() || !meta?.configured}>
              <Wand2 size={15} /> 合成
            </Button>
            {!meta?.configured && (
              <span className="text-xs text-warn">该引擎未配置，请先到设置页配置后使用。</span>
            )}
            {error && <span className="text-xs text-danger">{error}</span>}
            {results.length > 0 && (
              <Button variant="ghost" className="ml-auto" onClick={() => setResults([])}>
                清空结果
              </Button>
            )}
          </div>
        </Card>

        {results.length === 0 ? (
          <EmptyState
            title="还没有合成结果"
            desc="选好引擎和音色后点「合成」，结果会堆叠在这里方便并排对比试听（多次合成即 A/B 对比）。"
          />
        ) : (
          <div className="space-y-3">
            {results.map((r, i) => (
              <Card key={r.id} className="space-y-2">
                <div className="flex items-center gap-2 text-xs text-muted">
                  <Badge tone={i === 0 ? 'primary' : 'muted'}>#{results.length - i}</Badge>
                  <span className="font-medium text-text">{r.voiceName}</span>
                  <span>· {r.providerName}</span>
                  <span>· {r.speed.toFixed(2)}x</span>
                  <span>· {r.createdAt}</span>
                  {r.comboTag && <Badge tone="primary">{r.comboTag}</Badge>}
                  <div className="ml-auto flex items-center gap-1">
                    <button
                      title="下载"
                      onClick={() => download(r)}
                      className="rounded-md p-1.5 text-muted transition hover:bg-surface-2 hover:text-text"
                    >
                      <Download size={15} />
                    </button>
                    <button
                      title="删除"
                      onClick={() => {
                        URL.revokeObjectURL(r.url)
                        setResults((rs) => rs.filter((x) => x.id !== r.id))
                      }}
                      className="rounded-md p-1.5 text-muted transition hover:bg-surface-2 hover:text-danger"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Play size={16} className="shrink-0 text-primary" />
                  <audio controls src={r.url} className="h-9 w-full" />
                </div>
                <p className="line-clamp-2 text-xs text-muted">{r.text}</p>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
