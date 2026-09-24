#!/usr/bin/env python3
"""
fetch_chat.py — download a Twitch VOD chat replay to JSON with chat-downloader (2026-09-15).

Thin wrapper around the `chat_downloader` CLI (`uv tool install chat-downloader`, v0.2.8) that fixes
two things it gets wrong on Twitch VODs today:

  1. Twitch retired the persisted-query hash for the `VideoMetadata` GQL operation (the API answers
     `PersistedQueryNotFound`), and chat-downloader calls it first on every VOD — so every VOD download
     died with `'data' (KeyError)` after 15 retries even though the comments query itself still works.
     This wrapper sends `VideoMetadata` as plain GraphQL query text instead of the stale hash.
  2. chat-downloader's retry prompt polls stdin ("press Enter"), which eats the rest of a heredoc
     script and crashes on /dev/null. Retries here just sleep.

Every CLI flag passes straight through to chat_downloader. Runs under any python3: if the
chat_downloader package isn't importable it re-execs itself with the uv tool's interpreter.

Usage:
  python3 presets/gameplay/fetch_chat.py https://www.twitch.tv/videos/<id> \
      --output projects/<job>/chat/vod-<id>.json
Output (.json) = a JSON array of chat-downloader "twitch" messages:
  {message, time_in_seconds, timestamp, author:{id,name,display_name,colour,badges}, ...}
"""
import os
import re
import sys
import time

try:
    import chat_downloader  # noqa: F401
except ImportError:
    _alt = os.path.expanduser("~/.local/share/uv/tools/chat-downloader/bin/python")
    if os.path.exists(_alt) and os.path.realpath(sys.executable) != os.path.realpath(_alt):
        os.execv(_alt, [_alt, os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit("chat_downloader is not installed — run:  uv tool install chat-downloader")

from chat_downloader import cli
from chat_downloader.sites import common
from chat_downloader.sites.twitch import TwitchChatDownloader as _Twitch

# Operations whose persisted hash Twitch no longer knows → send as raw query text (same fields).
RAW_QUERIES = {
    "VideoMetadata": (
        "query VideoMetadata($videoID: ID!) { video(id: $videoID) { id title lengthSeconds createdAt "
        "owner { id login displayName } game { id displayName } } }"
    ),
}

_orig_download_gql = _Twitch._download_gql


def _download_gql(self, ops):
    if ops and all(op.get("operationName") in RAW_QUERIES for op in ops):
        raw = []
        for op in ops:
            q = RAW_QUERIES[op["operationName"]]
            declared = set(re.findall(r"\$(\w+)", q))
            raw.append({
                "operationName": op["operationName"],
                "query": q,
                "variables": {k: v for k, v in (op.get("variables") or {}).items() if k in declared},
            })
        return self._download_base_gql(raw)
    return _orig_download_gql(self, ops)


_Twitch._download_gql = _download_gql
# Retry back-off: plain sleep, never poll stdin.
common.timed_input = lambda timeout=0, *a, **k: time.sleep(timeout) if timeout and timeout > 0 else None

if __name__ == "__main__":
    sys.exit(cli.main())
