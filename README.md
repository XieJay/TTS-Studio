# TTS Studio

**本地优先的 Web 端文本转语音工作台** —— 上传稿件，选定音色，按语境合成出有呼吸感的配音。

单音色稿件配音 · 声音复刻 · 多角色对话配音 · AI 语境分析与剧本改编 · 多引擎合成（本地模型 / 云端 API）· 音频导出

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Node.js-18%2B-339933?logo=nodedotjs&logoColor=white" alt="Node.js 18+">
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black" alt="React 18">
  <img src="https://img.shields.io/badge/ffmpeg-required-0B75A9?logo=ffmpeg&logoColor=white" alt="ffmpeg">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

## 为什么是它

市面上的 TTS 工具要么是单次调用的「输入文本 → 出音频」，要么是绑定单一厂商的云服务。TTS Studio 把**一篇稿件的完整配音流程**做成了工作台：

- **逐句管理**：自动分句后，每一句都可以单独调整语气、语速、停顿，单独试听、单独重试；
- **语境感知**：LLM 通读全文，为每句建议情绪与停顿（如「庄重」「句后停 400ms」），预览后一键应用，也随时手动覆盖；
- **音色复用**：一段 5~30 秒的参考音频即可零样本克隆音色，一份音色档案可同时绑定到多个引擎（本地 / 云端），跨任务复用；
- **引擎无关**：插件式引擎适配层，同一个任务可随时切换引擎重新合成，前端零改动。

所有数据（SQLite + 音频文件）都保存在本地 `data/` 目录，无任何云端依赖。

## 功能一览

**稿件配音（核心场景）**
- 上传主持稿（txt / md / docx）或粘贴文本 → 智能分句（标点切分、引号保护、长句二次切分，可手动合并/拆分/排序）
- 任务级指定音色，个别句子可临时换音色（如标题句、公告句）
- 批量合成带 SSE 实时进度，失败句单独重试，已成功句不重复合成（断点续用）
- 逐句试听 / 整段连播（自动滚动高亮当前句）/ 合并版播放
- 导出 MP3 / WAV / ZIP（合并音频 + 逐句编号音频 + 稿件文本 + SRT 字幕）

**声音复刻与音色库**
- 上传 5~30s 参考音频，即时零样本克隆（本地引擎直接引用参考音频，云端引擎调用各自克隆 API）
- 音色档案与引擎解耦：一份音色可克隆/绑定到多个引擎，标注每个引擎的可用状态
- 支持录入内置音色（如 edge-tts 晓晓）统一管理

**多角色对话配音**
- `角色名: 台词` 纯文本剧本格式（中英冒号均可），`角色名(情绪): 台词` 可标注情绪，无冒号行归入旁白
- 角色绑定音色与默认表现力参数，按角色批量合成

**AI 能力（OpenAI 兼容 LLM）**
- 逐句语境分析：建议情绪 / 语气 / 停顿时长 / 语速倾向，预览勾选后应用
- 剧本改编：粘贴小说或文章，一键改写为多角色对话剧本（自动建立角色表，导入时可编辑）

**表现力控制**
- 语速（0.5~2.0×）/ 音调 / 音量滑杆，情绪预设 + 自由语气描述（instruct 引擎）
- 作用域三级：任务/角色默认 → 逐句覆盖 → 试炼场即席调节
- 引擎不支持语速时用 ffmpeg 变速兜底

**其他**
- 发音词典：多音字 / 人名读法替换（全局 + 任务级），只影响送入引擎的文本，不改原稿
- 试炼场 A/B 对比：同一句文本挂多个「引擎 + 音色」组合并排合成试听
- 浅色 / 深色 / 跟随系统三态主题，防刷新闪色

## 快速开始

### 环境要求

- Python 3.10+、Node.js 18+
- ffmpeg（合并导出 / SRT / 变速的硬依赖，缺失时单句合成仍可用，导出功能禁用）
  - Windows：`winget install Gyan.FFmpeg`

### 方式一：Windows 一键启动

双击 `start.bat` —— 自动清理端口残留、安装依赖、构建前端、启动服务并打开浏览器。

### 方式二：手动启动

```bash
# 后端（端口 8000）
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# 前端（端口 5173，另开终端；开发模式已配置代理到 8000）
cd frontend
npm install
npm run dev
```

开发模式访问 http://localhost:5173；生产模式构建前端后由 FastAPI 托管，单端口 8000：

```bash
cd frontend && npm run build
cd ../backend && python -m uvicorn app.main:app --port 8000
```

### 方式三：Docker

```bash
docker compose up -d   # 访问 http://127.0.0.1:8000，数据持久化在 ./data
```

### 零配置体验

不配置任何引擎也可以完整体验全流程：**edge-tts 免费内置**（微软音色，需联网）。打开「试炼场」输入文本即可合成、试听、下载。

## 引擎配置

在设置页为引擎填入地址 / 密钥，均带连通性测试；未配置的引擎在选择处自动置灰并引导。

| 引擎 | 需要配置 | 声音复刻 | 说明 |
|---|---|---|---|
| edge-tts | 无 | ❌ | 免费，需联网；内置中英文音色 |
| OpenAI 兼容接口 | base_url（+ api_key） | 视服务 | OpenAI 官方 / fish-speech 等通用 `/v1/audio/speech` |
| SiliconFlow | api_key | ✅ | 托管 CosyVoice2 / Fish Speech，注册送额度 |
| MiniMax | api_key + GroupId | ✅ | 情感参数丰富 |
| ElevenLabs | api_key | ✅ | 克隆效果最佳 |
| GPT-SoVITS | 服务地址 + **参考音频目录映射** | ✅ 零样本 | 本地自部署，见下文 |
| CosyVoice2 | 服务地址 + 参考音频目录映射 + 请求体模板 | ✅ 零样本 | 本地自部署，见下文 |
| IndexTTS-2.5 | Gradio WebUI 地址 | ✅ 零样本 | 本地自部署；参考音频经 HTTP 上传，无需目录映射 |

### 本地模型对接

三个本地引擎均要求用户自行部署模型服务（本项目只做对接，不负责部署）：

**GPT-SoVITS**：以 api_v2 模式启动其 API 服务后，在设置页填服务地址（如 `http://127.0.0.1:9880`）。其接口要求参考音频位于服务端本地磁盘，因此需配置「参考音频目录映射」——指定一个 GPT-SoVITS 进程可访问的目录，应用上传的参考音频会自动复制过去并按映射路径调用。

**CosyVoice2**：启动社区 API server 后填服务地址与 API 路径（默认 `/api/tts`）。不同实现的请求体不同，提供 JSON 模板（占位符 `{{text}}`、`{{ref_audio_path}}`、`{{speaker}}`）；同样需要配置参考音频目录映射。

**IndexTTS-2.5**：填 Gradio WebUI 地址（默认 `http://127.0.0.1:7860`）即可，参考音频直接经 HTTP 上传到服务端，无需目录映射。

> Docker 部署时，容器内访问宿主机模型用 `http://host.docker.internal:9880`（compose 已配置 host-gateway）。

### AI 能力配置

LLM 走 OpenAI 兼容接口：DeepSeek、通义、Kimi、本地 ollama 均可，设置页填 base_url / api_key / model 即可。

## 数据与安全

- 所有数据保存在本地 `data/` 目录：SQLite（配置 / 任务 / 音色 / 词典）+ 音频文件，整目录复制即可备份迁移
- **API key 明文存储于本地 SQLite**——这是单机个人工具的设计取舍。服务默认仅监听 `127.0.0.1`，请勿将端口暴露到公网；如需局域网访问，自行修改 `--host` 并自担风险
- 云端引擎按量计费：合成失败**不会自动重试**（防重复扣费），需手动重试

## 测试

```bash
cd backend
python -m pytest tests/ -v        # 单元测试（分句 / 发音替换 / 适配器参数与解码）
python -m tests.smoke_m3          # 端到端冒烟：建任务→批量合成→合并→SRT/ZIP（需服务已启动 + 联网）
python -m tests.mock_llm          # 本地模拟 LLM（验证 AI 链路，无需真实 key）
```

## 目录结构

```
TTS-Studio/
├─ backend/
│  └─ app/
│     ├─ api/          # 路由层：providers / settings / voices / tasks / jobs / tts / llm / export
│     ├─ services/     # 业务层：合成管线 / 文件解析与分句 / ffmpeg 音频处理 / LLM / 发音词典
│     └─ providers/    # 引擎适配层：统一 TTSProvider 抽象 × 8 个适配器
├─ frontend/src/       # React 18 + Vite + TypeScript + Tailwind（任务 / 试炼场 / 工作台 / 音色库 / 设置）
├─ data/               # 运行时数据（SQLite + 音频），可整目录备份
├─ start.bat           # Windows 一键启动
├─ Dockerfile
└─ docker-compose.yml
```

## 技术栈与架构

```
浏览器 (React SPA)
   │  REST /api/*            SSE /api/jobs/{id}/events
   ▼
FastAPI 路由层 (app/api/)
   ▼
业务层 (app/services/)   合成管线 · 解析分句 · 音频处理 · LLM · 发音词典
   ▼
引擎适配层 (app/providers/)   统一 TTSProvider.synthesize(SynthParams, VoiceRef)
   ▼
各 TTS 引擎（本地 HTTP / 云 API / edge-tts 库） + ffmpeg（合并 / SRT / 变速）
```

- **后端**：FastAPI + uvicorn + httpx（异步）、aiosqlite（SQLite WAL，无 ORM）、edge-tts、python-docx
- **前端**：React 18 + Vite 5 + TypeScript + TailwindCSS + TanStack Query 5 + zustand
- **音频处理**：ffmpeg / ffprobe 子进程（合并统一重采样 44.1kHz、SRT 时间轴、变速兜底）

扩展性设计：新增一个 TTS 引擎 = 在 `providers/` 下新增一个适配器文件并注册，前端零改动。

## Roadmap

- [ ] 自定义 HTTP 引擎（URL / 方法 / 头 / Body 模板，对接任意私有引擎）
- [ ] BGM 叠加混音导出
- [ ] 训练式微调克隆（对接 GPT-SoVITS 训练流程）
- [ ] PDF 导入、LRC / ASS 字幕格式
- [ ] 任务 / 音色打包导入导出备份
