# YT Tracker Skill — Bird 🐦

YouTube 頻道監控與分析推送。

## 模式說明

| 模式 | 觸發 | 分析深度 | 目標 |
|------|------|----------|------|
| `hourly` | 每 2h | 輕量（無 web_search，無轉錄）| 快速通知，<60s |
| `daily` | 每日 01:00 JST | 完整深度分析 | 深度研究報告 |

---

## Hourly 模式（輕量）

> ⚡ 目標：快速偵測新影片並即時通知，**不做深度分析**（省 token、省時間）

### Step 1 — 預檢

```bash
cd /home/node/.openclaw/workspace/projects/yt-tracker
python3 yt-check-new.py --frequency hourly
```

- `hasNew: false` → 回覆 **HEARTBEAT_OK**，結束
- `hasNew: true` → 繼續

### Step 2 — 推送即時通知（輕量格式）

對每部新影片，直接發送簡短通知（**不讀轉錄、不做 web_search**）：

```
📺 [頻道名] 新影片通知
🎬 [標題]
🔗 https://youtube.com/watch?v=[videoId]

⏰ 剛發布，詳細分析將於每日報告中呈現。
```

發送方式：`message` tool
- channel: telegram
- accountId: bird
- target: `-1003767828002`
- threadId: `36`

### Step 3 — 更新狀態

更新 `yt-tracker-state.json`：
- 把 videoId 加入 `lastNotifiedAt`（timestamp: 現在 UTC ISO 時間）
- 把 videoId 加入 `lastSeenVideoIds`

---

## Daily 模式（完整分析）

> 🔬 目標：深度分析每部影片，提供投資/科技洞察

### Step 1 — 預檢

```bash
cd /home/node/.openclaw/workspace/projects/yt-tracker
python3 yt-check-new.py --frequency daily
```

- `hasNew: false` → 回覆 **HEARTBEAT_OK**，結束
- `hasNew: true` → 繼續 Step 2

### Step 2 — 預載字幕/轉錄

```bash
cd /home/node/.openclaw/workspace/projects/yt-tracker
GROQ_KEY=$(python3 -c "import json; print(json.load(open('/home/node/.openclaw/agents/bird/agent/secrets/groq.json'))['GROQ_API_KEY'])")
PATH="$HOME/.deno/bin:$PATH" GROQ_API_KEY="$GROQ_KEY" python3 yt-preload.py -o /tmp/yt-preload-daily
```

讀取 `/tmp/yt-preload-daily/summary.json` 取得影片清單。

### Step 3 — 取得字幕/轉錄

優先順序：
1. **yt-dlp 自動字幕**（最快，免費）
2. **preload 的 Groq Whisper 轉錄**（無字幕時）
3. **影片描述 fallback**

```bash
cd /tmp
yt-dlp --write-auto-sub --sub-lang zh-Hant,zh-Hans,en --skip-download \
  --output "%(id)s" "https://www.youtube.com/watch?v={videoId}" 2>/dev/null

# 清理 VTT 取得純文字
python3 -c "
import re, sys
with open('{videoId}.en.vtt') as f: text = f.read()
lines, prev = [], ''
for line in text.split('\n'):
    if '-->' in line or line.strip().isdigit() or line.startswith('WEBVTT'): continue
    line = re.sub(r'<[^>]+>', '', line).strip()
    if line and line != prev: lines.append(line); prev = line
print(' '.join(lines))
" > {videoId}-transcript.txt
```

若 yt-dlp 失敗，改讀 `/tmp/yt-preload-daily/{videoId}.txt`。

### Step 4 — 分析每部影片

對每部影片：

1. **深度分析**：讀取完整 transcript，找出核心論點、數據、觀點
2. **外部驗證**：跑 **2-3 次** `web_search`
   - 搜尋影片標題 + 講者名 → 確認影片背景
   - 搜尋影片中提到的關鍵事件/數據 → 交叉驗證
3. **綜合撰寫**（300-500 字元）：
   - 📌 核心論點
   - 📊 關鍵數據（附外部驗證來源）
   - 💡 投資/科技啟示
   - ⚖️ 評價

### Step 5 — 推送 Telegram

格式：
```
📺 [頻道名] 每日分析
🎬 [標題]
🔗 https://youtube.com/watch?v=[videoId]

[分析內容]
```

發送方式：`message` tool
- channel: telegram
- accountId: bird
- target: `-1003767828002`
- threadId: `36`

### Step 6 — 更新狀態

更新 `yt-tracker-state.json`：
- 把 videoId 加入 `lastNotifiedAt`（timestamp: 現在 UTC ISO 時間）
- 把 videoId 加入 `lastSeenVideoIds`

---

## Step 7 — 存檔到 Obsidian + Push GitHub（Daily 模式必做）

每部影片分析完後，存成獨立 Obsidian note 並 push GitHub。

### Note 路徑
`/home/node/obsidian-vault/Projects/YT-Tracker/YYYY-MM-DD-{videoId}.md`

### Note 格式
```markdown
# {影片標題}

> **狀態**：✅ 已分析
> **日期**：YYYY-MM-DD
> **頻道**：{頻道名}
> **影片 ID**：{videoId}
> **URL**：https://youtube.com/watch?v={videoId}
> **字幕來源**：subtitles / whisper / description_fallback
> **評分**：⭐（1-5）

## 摘要
（一兩句話）

## 📌 核心論點
## 📊 關鍵數據
## 💡 核心洞察
## ⚖️ 評價

## Tags
#相關 #標籤
```

### 更新索引
在 `/home/node/obsidian-vault/Projects/YT-Tracker.md` 的「影片分析索引」區段加入新條目：
```
- [[YYYY-MM-DD-{videoId}]] — {頻道}：{標題摘要} ⭐
```

### Git Push
```bash
cd /home/node/obsidian-vault
git add -A
git commit -m "feat(yt-tracker): add video analysis {videoId} ({YYYY-MM-DD})"
git push
```

---

## 注意事項

- `lastNotifiedAt` 是去重的唯一依據，**不要依賴 `lastSeenVideoIds`**
- hourly 通知過的影片，daily 會因 `lastNotifiedAt` 已有記錄而**跳過**
  → 如需 daily 也分析，可設計 hourly 只加 `lastSeenVideoIds` 而不加 `lastNotifiedAt`（目前設計是通知即記錄）
- State file 位置：`/home/node/.openclaw/workspace/projects/yt-tracker/yt-tracker-state.json`
- Obsidian vault：`/home/node/obsidian-vault`（GitHub: openyhclaw-dot/obsidian-vault）
