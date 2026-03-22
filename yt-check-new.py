#!/usr/bin/env python3
"""
YT pre-check: fetch RSS for all tracked channels, compare against state.
Prints JSON with only channels that have new videos.
Exit 0 + empty newVideos = nothing new (skip LLM).
Exit 0 + non-empty newVideos = new videos found (trigger LLM).
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

STATE_FILE = Path(__file__).parent / "yt-tracker-state.json"
CHANNELS_FILE = Path(__file__).parent / "yt-channels.json"
RSS_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
TIMEOUT = 15


def fetch_rss(channel_id: str) -> list[dict]:
    """Fetch RSS and return list of {videoId, title, published}."""
    url = RSS_TEMPLATE.format(channel_id)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            xml_text = resp.read().decode("utf-8")
    except (URLError, Exception) as e:
        print(f"INFO: RSS failed for {channel_id}, will try yt-dlp: {e}", file=sys.stderr)
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        print(f"WARNING: Failed to parse RSS for {channel_id}", file=sys.stderr)
        return []

    entries = []
    for entry in root.findall("atom:entry", ns):
        vid = entry.find("yt:videoId", ns)
        title = entry.find("atom:title", ns)
        published = entry.find("atom:published", ns)
        if vid is not None:
            entries.append({
                "videoId": vid.text,
                "title": title.text if title is not None else "",
                "published": published.text if published is not None else "",
            })
    return entries


def fetch_via_ytdlp(channel_id: str, handle: str = "") -> list[dict]:
    """Fallback: use yt-dlp --flat-playlist to get recent videos."""
    if handle:
        url = f"https://www.youtube.com/{handle}/videos"
    else:
        url = f"https://www.youtube.com/channel/{channel_id}/videos"

    try:
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--dump-json", "--playlist-end", "5", url],
            capture_output=True, text=True, timeout=45,
        )
        entries = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                availability = d.get("availability", "") or ""
                members_only = availability.lower() in ("subscriber_only", "needs_auth", "premium")
                entries.append({
                    "videoId": d.get("id", ""),
                    "title": d.get("title", ""),
                    "published": "",
                    **({"membersOnly": True} if members_only else {}),
                })
            except json.JSONDecodeError:
                pass
        if entries:
            print(f"  yt-dlp got {len(entries)} videos for {handle or channel_id}", file=sys.stderr)
        return entries
    except Exception as e:
        print(f"WARNING: yt-dlp failed for {handle or channel_id}: {e}", file=sys.stderr)
        return []


STATE_EXPIRY_DAYS = 30


def prune_old_state(state: dict) -> tuple[dict, int]:
    """Remove entries older than STATE_EXPIRY_DAYS from lastNotifiedAt and lastSeenVideoIds.
    Returns (updated_state, pruned_count)."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=STATE_EXPIRY_DAYS)
    pruned = 0

    for cid, ch_state in state.get("channels", {}).items():
        lna = ch_state.get("lastNotifiedAt", {})
        expired_ids: set[str] = set()
        for vid_id, ts_str in list(lna.items()):
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < cutoff:
                    expired_ids.add(vid_id)
                    del lna[vid_id]
                    pruned += 1
            except (ValueError, TypeError):
                pass

        if expired_ids:
            ch_state["lastSeenVideoIds"] = [
                v for v in ch_state.get("lastSeenVideoIds", []) if v not in expired_ids
            ]

    # Prune top-level lastNotifiedAt
    top_lna = state.get("lastNotifiedAt", {})
    for vid_id, ts_str in list(top_lna.items()):
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts < cutoff:
                del top_lna[vid_id]
                pruned += 1
        except (ValueError, TypeError):
            pass

    # Prune top-level lastSeenVideoIds (keep only recent ones still in any channel's lastNotifiedAt)
    all_notified: set[str] = set()
    for ch_state in state.get("channels", {}).values():
        all_notified.update(ch_state.get("lastNotifiedAt", {}).keys())
    state["lastSeenVideoIds"] = [v for v in state.get("lastSeenVideoIds", []) if v in all_notified]

    return state, pruned


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--frequency", "-f", help="Filter by frequency (hourly/daily)")
    args = parser.parse_args()

    if not STATE_FILE.exists():
        print(json.dumps({"error": "state file not found"}))
        sys.exit(1)

    state = json.loads(STATE_FILE.read_text())

    # Prune expired state entries (>30 days)
    state, pruned_count = prune_old_state(state)
    if pruned_count > 0:
        print(f"INFO: Pruned {pruned_count} expired state entries (>{STATE_EXPIRY_DAYS}d)", file=sys.stderr)
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    # Load channel list from yt-channels.json (user-editable)
    # Falls back to state file channels if yt-channels.json doesn't exist
    if CHANNELS_FILE.exists():
        channel_list = json.loads(CHANNELS_FILE.read_text())
        channels = {}
        for ch in channel_list:
            if not ch.get("enabled", True):
                continue
            if args.frequency and ch.get("frequency", "daily") != args.frequency:
                continue
            cid = ch["channelId"]
            # Merge with state data (preserves lastSeenVideoIds etc.)
            state_ch = state.get("channels", {}).get(cid, {})
            channels[cid] = {
                **state_ch,
                "name": ch.get("name", state_ch.get("name", "")),
                "handle": ch.get("handle", state_ch.get("handle", "")),
                "category": ch.get("category", state_ch.get("category", "")),
            }
            # Initialize state entry for new channels
            if cid not in state.get("channels", {}):
                state.setdefault("channels", {})[cid] = {
                    "name": ch.get("name", ""),
                    "handle": ch.get("handle", ""),
                    "category": ch.get("category", ""),
                    "lastSeenVideoIds": [],
                }
                STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                print(f"NEW CHANNEL added to state: {ch.get('name', cid)}", file=sys.stderr)
    else:
        channels = state.get("channels", {})

    # Phase 1: Fetch all RSS in parallel
    results = {}
    rss_failed = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(fetch_rss, cid): cid for cid in channels
        }
        for future in as_completed(futures):
            cid = futures[future]
            try:
                entries = future.result()
                if entries:
                    results[cid] = entries
                else:
                    rss_failed.append(cid)
            except Exception as e:
                print(f"WARNING: {cid} error: {e}", file=sys.stderr)
                rss_failed.append(cid)

    # Phase 2: For failed RSS, use yt-dlp fallback (sequential to avoid throttling)
    if rss_failed:
        print(f"Using yt-dlp fallback for {len(rss_failed)} channels...", file=sys.stderr)
        for cid in rss_failed:
            handle = channels.get(cid, {}).get("handle", "")
            entries = fetch_via_ytdlp(cid, handle)
            if entries:
                results[cid] = entries

    # Compare against state — use lastNotifiedAt keys as ground truth
    # (lastSeenVideoIds is unreliable: yt-dlp fallback may bulk-add unsent videos)
    # membersOnlyIds: videos confirmed members-only — skip until they go public
    # Auto-graduate: if a membersOnly video now appears in RSS without membersOnly flag, treat as newly public
    new_videos = {}
    for cid, entries in results.items():
        notified = set(channels.get(cid, {}).get("lastNotifiedAt", {}).keys())
        members_only_ids = channels.get(cid, {}).get("membersOnlyIds", [])
        members_only = set(members_only_ids)
        rss_ids = {e["videoId"] for e in entries}

        # Check if any membersOnly video is now public (in RSS and not flagged as membersOnly)
        newly_public = []
        for vid in list(members_only_ids):
            if vid in rss_ids:
                matching = next((e for e in entries if e["videoId"] == vid), None)
                if matching and not matching.get("membersOnly"):
                    print(f"INFO: {vid} graduated from members-only to public!", file=sys.stderr)
                    newly_public.append(vid)
                    members_only.discard(vid)

        if newly_public:
            # Update state: remove from membersOnlyIds
            state_ch = state["channels"].get(cid, {})
            state_ch["membersOnlyIds"] = [v for v in state_ch.get("membersOnlyIds", []) if v not in newly_public]
            state["channels"][cid] = state_ch
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

        new_entries = [
            e for e in entries
            if e["videoId"] not in notified and e["videoId"] not in members_only
        ]
        if new_entries:
            new_videos[cid] = {
                "name": channels.get(cid, {}).get("name", cid),
                "videos": new_entries,
            }

    output = {
        "hasNew": len(new_videos) > 0,
        "newVideos": new_videos,
        "checkedChannels": len(channels),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
