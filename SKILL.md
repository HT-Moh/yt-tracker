# YT Tracker Skill — Bird 🐦

YouTube 頻道監控與分析推送。

## 執行流程

### Step 1 — 預檢（Pre-check）

```bash
cd /home/node/.openclaw/workspace/projects/yt-tracker
PATH="$HOME/.deno/bin:$PATH" python3 yt-check-new.py --frequency ${FREQUENCY}
```

- `${FREQUENCY}` = `hourly` 或 `daily`，由 cron message 指定
- 如果 `hasNew: false` → 回覆 **HEARTBEAT_OK**，結束
- 如果 `hasNew: true` → 繼續 Step 2

### Step 2 — 預載字幕/轉錄

```bash
cd /home/node/.openclaw/workspace/projects/yt-tracker
## 先讀取 API key：
GROQ_KEY=$(python3 -c "import json; print(json.load(open('/home/node/.openclaw/agents/bird/agent/secrets/groq.json'))['GROQ_API_KEY'])")

PATH="$HOME/.deno/bin:$PATH" GROQ_API_KEY="$GROQ_KEY" python3 yt-preload.py -o /tmp/yt-preload-${FREQUENCY}
```

讀取 `/tmp/yt-preload-${FREQUENCY}/summary.json` 取得影片清單。

### Step 3 — 分析每部影片

對每部影片：

1. **分析**：讀取 `/tmp/yt-preload-${FREQUENCY}/{videoId}.txt`，找出核心論點、數據、觀點
2. **查證**：跑 2-4 次 `web_search` 驗證關鍵主張、補充上下文
3. **綜合撰寫**（500+ 字元）：
   - 📌核心論點
   - 📊關鍵數據
   - 🔍邏輯推演
   - 💡投資啟示
   - ⚖️個人評價

### Step 4 — 推送 Telegram

格式：
```
📺 [頻道名]新影片
🎬 [標題]
🔗 https://youtube.com/watch?v=[videoId]

[分析內容]
```

發送方式：`message` tool
- channel: telegram
- accountId: bird
- target: ${TELEGRAM_CHAT_ID}
- threadId: ${TELEGRAM_THREAD_ID}

### Step 5 — 更新狀態

更新 `yt-tracker-state.json`（同目錄）：
- 把 videoId 加入 `lastSeenVideoIds`
- 更新 `lastNotifiedAt`
