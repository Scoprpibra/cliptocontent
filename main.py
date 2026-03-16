import os
import re
from flask import Flask, request, render_template_string
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    RequestBlocked,
    IpBlocked,
)

app = Flask(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ClipToContent</title>
<style>
body{font-family:Arial;background:#f4f6fb;padding:40px}
.box{max-width:900px;margin:auto;background:white;padding:30px;border-radius:12px}
input{width:75%;padding:12px;font-size:16px}
button{padding:12px 20px;background:#22c55e;border:none;color:white;font-weight:bold;border-radius:8px;cursor:pointer}
.error{background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px;margin-top:15px}
.result{background:#f1f5f9;padding:20px;margin-top:20px;border-radius:10px}
pre{white-space:pre-wrap;font-family:Arial,sans-serif}
</style>
</head>
<body>
<div class="box">
<h1>ClipToContent</h1>
<p>Turn 1 YouTube video into hooks, posts, threads, summaries and a content plan.</p>

<form method="POST" action="/generate">
<input type="text" name="youtube_url" placeholder="Paste YouTube link here" value="{{ youtube_url or '' }}" required>
<button type="submit">Generate</button>
</form>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

{% if result %}
<div class="result">
<h2>Content Pack</h2>
<pre>{{ result }}</pre>
</div>
{% endif %}

</div>
</body>
</html>
"""


def get_video_id(url: str) -> str:
    patterns = [
        r"(?:v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:embed/)([A-Za-z0-9_-]{11})",
        r"(?:shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Invalid YouTube URL")


def build_transcript_client() -> YouTubeTranscriptApi:
    proxy_host = os.environ.get("PROXY_HOST")
    proxy_port = os.environ.get("PROXY_PORT")
    proxy_user = os.environ.get("PROXY_USERNAME")
    proxy_pass = os.environ.get("PROXY_PASSWORD")

    if proxy_host and proxy_port and proxy_user and proxy_pass:
        proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
        proxy_config = GenericProxyConfig(
            http_url=proxy_url,
            https_url=proxy_url,
        )
        return YouTubeTranscriptApi(proxy_config=proxy_config)

    return YouTubeTranscriptApi()


def fetch_transcript(video_id: str) -> str:
    api = build_transcript_client()

    try:
        fetched = api.fetch(video_id, languages=["en"])
        return " ".join(snippet.text for snippet in fetched)
    except NoTranscriptFound:
        raise
    except (TranscriptsDisabled, VideoUnavailable, RequestBlocked, IpBlocked):
        raise
    except Exception as e:
        raise RuntimeError(f"Transcript fetch failed: {str(e)}") from e


@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML, result=None, error=None, youtube_url="")


@app.route("/generate", methods=["POST"])
def generate():
    youtube_url = request.form.get("youtube_url", "").strip()

    try:
        video_id = get_video_id(youtube_url)
        transcript = fetch_transcript(video_id)

        if not transcript or len(transcript.strip()) < 50:
            raise RuntimeError("Transcript was too short or unavailable.")

        prompt = f"""
You are a YouTube content repurposing expert.

Based on this transcript generate:

1. Short Summary
2. 10 Viral Hooks
3. LinkedIn Post
4. Twitter/X Thread
5. Key Bullet Points
6. YouTube Description
7. Blog Outline
8. 7 Day Content Distribution Plan

Transcript:
{transcript[:4000]}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        result = response.choices[0].message.content

        return render_template_string(
            HTML,
            result=result,
            error=None,
            youtube_url=youtube_url,
        )

    except ValueError:
        return render_template_string(
            HTML,
            result=None,
            error="Invalid YouTube URL. Paste a full YouTube link.",
            youtube_url=youtube_url,
        )

    except TranscriptsDisabled:
        return render_template_string(
            HTML,
            result=None,
            error="Transcripts are disabled for this video.",
            youtube_url=youtube_url,
        )

    except NoTranscriptFound:
        return render_template_string(
            HTML,
            result=None,
            error="No transcript was found for this video.",
            youtube_url=youtube_url,
        )

    except VideoUnavailable:
        return render_template_string(
            HTML,
            result=None,
            error="This video is unavailable.",
            youtube_url=youtube_url,
        )

    except (RequestBlocked, IpBlocked):
        return render_template_string(
            HTML,
            result=None,
            error="We couldn’t retrieve captions for this video right now. Please try another video.",
            youtube_url=youtube_url,
        )

    except Exception:
        return render_template_string(
            HTML,
            result=None,
            error="We couldn’t retrieve captions for this video right now. Please try another video.",
            youtube_url=youtube_url,
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

