export type ProviderType = 'builtin' | 'local' | 'cloud'

export interface Capabilities {
  clone: boolean
  pitch: boolean
  emotion: boolean
  instruct: boolean
  builtin_voices: boolean
}

export interface ProviderInfo {
  id: string
  name: string
  type: ProviderType
  description: string
  needs_config: boolean
  free: boolean
  capabilities: Capabilities
  configured: boolean
}

export interface BuiltinVoice {
  name: string
  display_name: string
  gender: string
  language: string
}

export interface VoiceRef {
  kind: 'builtin' | 'ref_audio' | 'cloud_id'
  voice_name?: string | null
  ref_audio_path?: string | null
  prompt_text?: string | null
  prompt_lang?: string | null
  cloud_voice_id?: string | null
}

export interface SynthParams {
  text: string
  speed: number
  pitch?: number | null
  volume: number
  emotion?: string | null
  instruct?: string | null
  language?: string | null
}

export interface SystemStatus {
  ffmpeg: boolean
  data_dir: string
}

export interface ProviderSettings {
  providers: Record<string, Record<string, unknown>>
  llm: { base_url: string; api_key: string; model: string }
}
