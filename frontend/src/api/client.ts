export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle(res: Response): Promise<Response> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const j = await res.json()
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* 保留默认消息 */
    }
    throw new ApiError(res.status, msg)
  }
  return res
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await handle(await fetch(path))
  return r.json() as Promise<T>
}

export async function apiSend<T>(
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T> {
  const r = await handle(
    await fetch(path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  )
  return r.json() as Promise<T>
}

/** 调用返回音频流的接口 */
export async function apiAudio(path: string, body: unknown): Promise<{ blob: Blob; format: string }> {
  const r = await handle(
    await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
  return { blob: await r.blob(), format: r.headers.get('X-Audio-Format') || 'mp3' }
}

/** 上传 multipart */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const r = await handle(await fetch(path, { method: 'POST', body: form }))
  return r.json() as Promise<T>
}
