"""YouTube'ga yuklash (yopiq/private holatda, admin tasdiqlashi uchun)."""
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from . import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]


def _service():
    creds = Credentials(
        token=None, refresh_token=config.YT_REFRESH_TOKEN(),
        client_id=config.YT_CLIENT_ID(), client_secret=config.YT_CLIENT_SECRET(),
        token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video: Path, thumbnail: Path, title: str, description: str, tags: list[str]) -> tuple[str, str | None]:
    yt = _service()
    body = {
        "snippet": {
            "title": title[:100], "description": description[:4900],
            "tags": tags[:30], "categoryId": "27",  # Education
            "defaultLanguage": "uz", "defaultAudioLanguage": "uz",
        },
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "embeddable": True},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024,
                                                        resumable=True, mimetype="video/mp4"))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    thumb_err = None
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumbnail))).execute()
    except Exception as e:  # kanal telefon orqali tasdiqlanmagan bo'lsa ishlamaydi
        thumb_err = str(e)[:200]
    return vid, thumb_err
