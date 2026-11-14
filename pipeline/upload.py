"""YouTube Data API v3 upload (resumable) using a stored refresh token."""
from __future__ import annotations

import os
import random
import time
from pathlib import Path

from .utils import log

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video: Path, title: str, description: str, tags: list[str], cfg: dict) -> str:
    from google.auth.exceptions import RefreshError
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    up = cfg["upload"]
    status = {
        "privacyStatus": up.get("privacy", "public"),
        "selfDeclaredMadeForKids": bool(up.get("made_for_kids", False)),
        "embeddable": True,
        "publicStatsViewable": True,
    }
    if up.get("contains_synthetic_media") is not None:
        status["containsSyntheticMedia"] = bool(up["contains_synthetic_media"])
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags,
            "categoryId": str(up.get("category_id", "28")),
            "defaultLanguage": "id",
            "defaultAudioLanguage": "id",
        },
        "status": status,
    }
    yt = _service()
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp, attempt = None, 0
    while resp is None:
        try:
            progress, resp = req.next_chunk()
            if progress:
                log.info("upload %d%%", int(progress.progress() * 100))
        except RefreshError as exc:
            raise RuntimeError(
                "YouTube refresh token rejected (invalid_grant). Typical causes: OAuth consent screen still in "
                "'Testing' (tokens expire after ~7 days), token revoked, or client id/secret do not match the token. "
                "Set the app to 'In production', regenerate YT_REFRESH_TOKEN and update the GitHub secret. "
                f"Details: {str(exc)[:200]}") from exc
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and attempt < 6:
                attempt += 1
                wait = min(60, 2 ** attempt + random.random())
                log.warning("upload hiccup %s, retry in %.0fs", exc.resp.status, wait)
                time.sleep(wait)
                continue
            raise
    vid = resp["id"]
    log.info("uploaded: https://youtube.com/shorts/%s", vid)
    return vid
