#!/usr/bin/env python3
"""
gemini-analyze.py — Analyze YouTube videos via Gemini 2.5 Flash
================================================================
Sends YouTube URL directly to Gemini for deep analysis. No download needed.

Usage:
  python3 gemini-analyze.py --url "https://youtube.com/watch?v=xxx"
  python3 gemini-analyze.py --url "https://youtube.com/watch?v=xxx" --mode daily
  python3 gemini-analyze.py --url "https://youtube.com/watch?v=xxx" --json

Environment:
  GEMINI_API_KEY — Google AI Studio API key (required)
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

HOURLY_PROMPT = """你是一位專業的影片分析師。請分析這支 YouTube 影片，提供以下內容（用繁體中文）：

1. **核心主題**（2-3 行）：影片在講什麼，為什麼值得看
2. **關鍵洞察**（1-2 個最重要的觀點或數據）
3. **講者背景**（一句話描述講者是誰）

保持簡潔有力，總共不超過 200 字。"""

DAILY_PROMPT = """你是一位具有批判性思維的專業影片分析師。請對這支 YouTube 影片進行詳盡、客觀的深度分析（用繁體中文）：

## 分析要求

### 📌 核心論點摘要
- 影片的主要論點和立場是什麼？
- 講者試圖說服觀眾什麼？

### 📊 關鍵數據與事實
- 影片中提到的具體數據、統計、事件
- 標注哪些是可驗證的事實，哪些是講者的推測

### 🔍 批判性分析
- **立場偏差**：講者有什麼明顯的立場或利益衝突？
- **邏輯漏洞**：論證中有沒有跳躍、假設未被驗證、或以偏概全？
- **缺失觀點**：哪些重要的反面觀點或替代解釋被忽略了？
- **資訊品質**：引用的來源可靠嗎？有沒有過度簡化複雜議題？

### 💡 核心洞察
- 這支影片最有價值的 1-2 個觀點是什麼？
- 對投資者/科技從業者有什麼啟示？

### ⚖️ 綜合評價
- 推薦度（1-5 ⭐）
- 一句話總結：值得看的理由 or 可以跳過的理由

保持客觀中立。如果影片品質低或觀點偏頗，請直說。總共 300-500 字。"""


def analyze_video(youtube_url: str, mode: str = "hourly") -> dict:
    """Send YouTube URL to Gemini for analysis."""
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY not set", "success": False}

    prompt = DAILY_PROMPT if mode == "daily" else HOURLY_PROMPT

    # Build request
    url = f"{API_BASE}/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "fileData": {
                            "mimeType": "video/mp4",
                            "fileUri": youtube_url
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4096,
        }
    }

    # Try with fileData (YouTube URL) first
    # If that fails, try with just the URL as text
    for attempt in range(2):
        try:
            if attempt == 1:
                # Fallback: send URL as text instead of fileData
                payload["contents"][0]["parts"] = [
                    {"text": f"{prompt}\n\nYouTube 影片連結：{youtube_url}\n\n請根據你對這支影片的了解進行分析。如果無法存取影片內容，請根據影片標題和頻道資訊提供你能提供的分析。"}
                ]

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # Extract text from response
            candidates = result.get("candidates", [])
            if not candidates:
                if attempt == 0:
                    continue
                return {"error": "No response from Gemini", "success": False}

            text = ""
            for part in candidates[0].get("content", {}).get("parts", []):
                if "text" in part:
                    text += part["text"]

            if not text.strip():
                if attempt == 0:
                    continue
                return {"error": "Empty response from Gemini", "success": False}

            # Token usage
            usage = result.get("usageMetadata", {})

            return {
                "success": True,
                "analysis": text.strip(),
                "model": MODEL,
                "mode": mode,
                "url": youtube_url,
                "tokens": {
                    "input": usage.get("promptTokenCount", 0),
                    "output": usage.get("candidatesTokenCount", 0),
                    "total": usage.get("totalTokenCount", 0),
                },
                "attempt": attempt + 1,
            }

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except:
                pass

            if attempt == 0 and (e.code == 400 or "INVALID_ARGUMENT" in error_body):
                # fileData approach failed, try text-only fallback
                continue

            return {
                "error": f"HTTP {e.code}: {error_body[:500]}",
                "success": False,
            }

        except Exception as e:
            if attempt == 0:
                continue
            return {"error": str(e), "success": False}

    return {"error": "All attempts failed", "success": False}


def main():
    parser = argparse.ArgumentParser(description="Analyze YouTube video via Gemini")
    parser.add_argument("--url", "-u", required=True, help="YouTube video URL")
    parser.add_argument("--mode", "-m", default="hourly", choices=["hourly", "daily"],
                        help="Analysis depth (hourly=brief, daily=deep critical)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    result = analyze_video(args.url, args.mode)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print(f"Model: {result['model']} (attempt {result['attempt']})")
            print(f"Mode:  {result['mode']}")
            print(f"Tokens: {result['tokens']['input']} in / {result['tokens']['output']} out")
            print(f"URL:   {result['url']}")
            print("─" * 60)
            print(result["analysis"])
        else:
            print(f"❌ Error: {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
