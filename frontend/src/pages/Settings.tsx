import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, PlugZap, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiGet, apiSend } from '../api/client'
import type { ProviderInfo, ProviderSettings, SystemStatus } from '../api/types'
import { Badge, Button, Card, Spinner, TextInput } from '../components/ui'

interface FieldDef {
  key: string
  label: string
  type?: 'text' | 'password' | 'checkbox'
  placeholder?: string
}

const PROVIDER_FIELDS: Record<string, FieldDef[]> = {
  openai_compat: [
    { key: 'base_url', label: 'Base URL', placeholder: 'https://api.openai.com/v1 或 http://127.0.0.1:8080/v1' },
    { key: 'api_key', label: 'API Key', type: 'password', placeholder: '本地服务可留空' },
    { key: 'model', label: '模型名', placeholder: 'tts-1 / tts-1-hd / gpt-4o-mini-tts / fish-speech-1.5' },
    { key: 'default_voice', label: '默认音色', placeholder: 'alloy' },
    { key: 'voices', label: '音色列表（逗号分隔）', placeholder: 'alloy,echo,fable,onyx,nova,shimmer' },
    { key: 'instruct_support', label: '支持 instructions 语气描述', type: 'checkbox' },
  ],
  siliconflow: [
    { key: 'api_key', label: 'API Key', type: 'password', placeholder: '在 siliconflow.cn 获取' },
    { key: 'model', label: '模型', placeholder: 'FunAudioLLM/CosyVoice2-0.5B' },
  ],
  gptsovits: [
    { key: 'base_url', label: '服务地址（api_v2）', placeholder: 'http://127.0.0.1:9880' },
    { key: 'ref_dir', label: '参考音频目录映射', placeholder: 'GPT-SoVITS 服务进程可访问的目录，如 D:/GPT-SoVITS/refs' },
    { key: 'text_lang', label: '台词语言', placeholder: 'zh / en / ja（默认 zh）' },
    { key: 'prompt_lang', label: '参考音频语言', placeholder: 'zh（默认）' },
  ],
  cosyvoice: [
    { key: 'base_url', label: '服务地址', placeholder: 'http://127.0.0.1:5000' },
    { key: 'api_path', label: 'API 路径', placeholder: '/api/tts（默认）' },
    { key: 'ref_dir', label: '参考音频目录映射', placeholder: 'CosyVoice 服务进程可访问的目录' },
    { key: 'speaker', label: '说话人（可选）', placeholder: '按你的部署填写' },
    {
      key: 'body_template', label: '请求体模板（JSON，支持 {{text}} {{ref_audio_path}} {{speaker}}）',
      placeholder: '{"text": "{{text}}", "ref_audio_path": "{{ref_audio_path}}"}',
    },
  ],
  minimax: [
    { key: 'api_key', label: 'API Key', type: 'password' },
    { key: 'group_id', label: 'Group ID', placeholder: 'MiniMax 控制台查看' },
    { key: 'model', label: '模型', placeholder: 'speech-02-hd / speech-02-turbo' },
  ],
  elevenlabs: [
    { key: 'api_key', label: 'API Key', type: 'password' },
    { key: 'model', label: '模型', placeholder: 'eleven_multilingual_v2' },
    { key: 'default_voice_id', label: '默认 Voice ID（选填）' },
  ],
  indextts: [
    { key: 'base_url', label: '服务地址（Gradio WebUI）', placeholder: 'http://127.0.0.1:7860' },
  ],
}

export default function Settings() {
  const { data: sys } = useQuery({
    queryKey: ['system'],
    queryFn: () => apiGet<SystemStatus>('/api/system/status'),
  })
  const { data: providers = [], refetch: refetchProviders } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiGet<ProviderInfo[]>('/api/providers'),
  })
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiGet<ProviderSettings>('/api/settings'),
  })
  const [drafts, setDrafts] = useState<Record<string, Record<string, unknown>>>({})
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; message: string }>>({})
  const [saving, setSaving] = useState<string>('')
  const [testing, setTesting] = useState<string>('')
  const [llmDraft, setLlmDraft] = useState<{ base_url: string; api_key: string; model: string }>({
    base_url: '', api_key: '', model: '',
  })
  const [llmLoaded, setLlmLoaded] = useState(false)
  const [globalRules, setGlobalRules] = useState<{ id: string; find: string; replace: string }[]>([])
  const [ruleFind, setRuleFind] = useState('')
  const [ruleReplace, setRuleReplace] = useState('')
  const [addingRule, setAddingRule] = useState(false)

  const loadRules = async () => {
    const r = await apiGet<{ global: { id: string; find: string; replace: string }[] }>('/api/pronunciations')
    setGlobalRules(r.global)
  }
  useEffect(() => {
    loadRules().catch(() => {})
  }, [])
  useEffect(() => {
    if (settingsQuery.data?.llm && !llmLoaded) {
      setLlmDraft({ ...settingsQuery.data.llm })
      setLlmLoaded(true)
    }
  }, [settingsQuery.data, llmLoaded])

  const draftOf = (id: string): Record<string, unknown> => {
    if (drafts[id]) return drafts[id]
    return settingsQuery.data?.providers?.[id] ?? {}
  }
  const setField = (id: string, key: string, value: unknown) =>
    setDrafts((d) => ({ ...d, [id]: { ...draftOf(id), [key]: value } }))

  const save = async (id: string) => {
    setSaving(id)
    try {
      await apiSend(`/api/settings/providers/${id}`, 'PUT', draftOf(id))
      await refetchProviders()
    } finally {
      setSaving('')
    }
  }

  const test = async (id: string) => {
    setTesting(id)
    try {
      const r = await apiSend<{ ok: boolean; message: string }>(`/api/settings/test/providers/${id}`, 'POST')
      setTestResults((t) => ({ ...t, [id]: r }))
    } catch (e) {
      setTestResults((t) => ({ ...t, [id]: { ok: false, message: e instanceof Error ? e.message : String(e) } }))
    } finally {
      setTesting('')
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-semibold">设置</h1>

      {sys && !sys.ffmpeg && (
        <Card className="flex items-start gap-3 border-warn/40 bg-warn/5">
          <AlertTriangle className="mt-0.5 text-warn" size={18} />
          <div className="text-sm">
            <div className="font-medium">未检测到 ffmpeg</div>
            <div className="mt-1 text-muted">
              单句合成与试听不受影响；整段合并、SRT 字幕、变速兜底需要 ffmpeg。安装：{' '}
              <code className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">winget install Gyan.FFmpeg</code>（安装后重启本应用生效）
            </div>
          </div>
        </Card>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted">TTS 引擎</h2>
        {providers.map((p) => {
          const fields = PROVIDER_FIELDS[p.id] ?? []
          return (
            <Card key={p.id} className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.name}</span>
                <Badge tone={p.configured ? 'ok' : 'muted'}>{p.configured ? '已配置' : '未配置'}</Badge>
                {p.free && <Badge tone="ok">免费</Badge>}
                {p.type === 'local' && <Badge>本地</Badge>}
                {p.type === 'cloud' && <Badge>云端</Badge>}
              </div>
              <p className="text-xs text-muted">{p.description}</p>

              {fields.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {fields.map((f) => {
                    const v = draftOf(p.id)[f.key]
                    return (
                      <div key={f.key}>
                        <label className="mb-1 block text-xs text-muted">{f.label}</label>
                        {f.type === 'checkbox' ? (
                          <label className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={Boolean(v)}
                              onChange={(e) => setField(p.id, f.key, e.target.checked)}
                            />
                            启用
                          </label>
                        ) : (
                          <TextInput
                            type={f.type ?? 'text'}
                            placeholder={f.placeholder}
                            value={typeof v === 'string' ? v : ''}
                            onChange={(e) => setField(p.id, f.key, e.target.value)}
                          />
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-muted">该引擎无需配置。</p>
              )}

              {fields.length > 0 && (
                <div className="flex items-center gap-3">
                  <Button variant="outline" loading={saving === p.id} onClick={() => save(p.id)}>
                    <Save size={14} /> 保存
                  </Button>
                  <Button variant="ghost" loading={testing === p.id} onClick={() => test(p.id)}>
                    <PlugZap size={14} /> 测试连接
                  </Button>
                  {testResults[p.id] && (
                    <span className={`text-xs ${testResults[p.id].ok ? 'text-ok' : 'text-danger'}`}>
                      {testResults[p.id].message}
                    </span>
                  )}
                  {saving === p.id && <Spinner />}
                </div>
              )}
            </Card>
          )
        })}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted">发音词典（全局）</h2>
        <Card className="space-y-3">
          <p className="text-xs text-muted">全局替换规则（如多音字、人名读法），对所有任务生效；任务级规则在各任务的工作台内维护，优先级更高。</p>
          <div className="space-y-1">
            {globalRules.map((r) => (
              <div key={r.id} className="flex items-center gap-2 rounded-lg border border-border p-2 text-sm">
                <span className="font-medium">{r.find}</span>
                <span className="text-muted">→</span>
                <span className="flex-1 text-primary">{r.replace || '（删除）'}</span>
                <button
                  className="text-muted hover:text-danger"
                  onClick={() => apiSend(`/api/pronunciations/${r.id}`, 'DELETE').then(loadRules)}
                >
                  ✕
                </button>
              </div>
            ))}
            {globalRules.length === 0 && <p className="text-xs text-muted">暂无规则。</p>}
          </div>
          <div className="flex gap-2">
            <TextInput placeholder="原文" value={ruleFind} onChange={(e) => setRuleFind(e.target.value)} />
            <TextInput placeholder="替换为" value={ruleReplace} onChange={(e) => setRuleReplace(e.target.value)} />
            <Button
              className="shrink-0"
              disabled={!ruleFind.trim()}
              loading={addingRule}
              onClick={async () => {
                setAddingRule(true)
                try {
                  await apiSend('/api/pronunciations', 'POST', { scope: 'global', find: ruleFind, replace: ruleReplace })
                  setRuleFind('')
                  setRuleReplace('')
                  await loadRules()
                } finally {
                  setAddingRule(false)
                }
              }}
            >
              添加
            </Button>
          </div>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted">LLM（AI 语境分析 / 剧本改编）</h2>
        <Card className="space-y-3">
          <p className="text-xs text-muted">配置任意 OpenAI 兼容接口（DeepSeek / 通义 / Kimi / 本地 ollama 等），用于 AI 语境分析与剧本改编。</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-muted">Base URL</label>
              <TextInput
                placeholder="https://api.deepseek.com/v1 或 http://127.0.0.1:11434/v1"
                value={llmDraft.base_url}
                onChange={(e) => setLlmDraft({ ...llmDraft, base_url: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted">API Key</label>
              <TextInput
                type="password"
                value={llmDraft.api_key}
                onChange={(e) => setLlmDraft({ ...llmDraft, api_key: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted">模型名</label>
              <TextInput
                placeholder="deepseek-chat / qwen-plus / llama3"
                value={llmDraft.model}
                onChange={(e) => setLlmDraft({ ...llmDraft, model: e.target.value })}
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              loading={saving === 'llm'}
              onClick={async () => {
                setSaving('llm')
                try {
                  await apiSend('/api/settings/llm', 'PUT', llmDraft)
                } finally {
                  setSaving('')
                }
              }}
            >
              <Save size={14} /> 保存
            </Button>
            <Button
              variant="ghost"
              loading={testing === 'llm'}
              onClick={async () => {
                setTesting('llm')
                try {
                  const r = await apiSend<{ ok: boolean; message: string }>('/api/llm/test', 'POST')
                  setTestResults((t) => ({ ...t, llm: r }))
                } catch (e) {
                  setTestResults((t) => ({ ...t, llm: { ok: false, message: e instanceof Error ? e.message : String(e) } }))
                } finally {
                  setTesting('')
                }
              }}
            >
              <PlugZap size={14} /> 测试连接
            </Button>
            {testResults.llm && (
              <span className={`text-xs ${testResults.llm.ok ? 'text-ok' : 'text-danger'}`}>{testResults.llm.message}</span>
            )}
          </div>
        </Card>
      </section>
    </div>
  )
}
