import os
import re
from flask import Flask, request, render_template_string
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

app = Flask(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ClipToContent</title>
<style>
body{font-family:Arial;background:#f4f6fb;padding:40px}
.box{max-width:900px;margin:auto;background:white;padding:30px;border-radius:12px}
input{width:75%;padding:12px;font-size:16px}
button{padding:12px 20px;background:#22c55e;border:none;color:white;font-weight:bold;border-radius:8px}
.error{background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px;margin-top:15px}
.result{background:#f1f5f9;padding:20px;margin-top:20px;border-radius:10px}
</style>
</head>
<body>
<div class="box">
<h1>ClipToContent</h1>
<p>Turn 1 YouTube video into hooks, posts, threads, summaries and a content plan.</p>

<form method="POST" action="/generate">
<input type="text" name="youtube_url" placeholder="Paste YouTube link here" required>
<button type="submit">Generate</button>
</form>

{% if error %}
<div class="error">{{error}}</div>
{% endif %}

{% if result %}
<div class="result">
<pre>{{result}}</pre>
</div>
{% endif %}

</div>
</body>
</html>
"""


def get_video_id(url):
    pattern = r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    raise ValueError("Invalid YouTube URL")


def fetch_transcript(video_id):
    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
    text = " ".join(chunk["text"] for chunk in transcript)
    return text


@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML)


@app.route("/generate", methods=["POST"])
def generate():

    url = request.form.get("youtube_url")

    try:
        video_id = get_video_id(url)

        transcript = fetch_transcript(video_id)

        prompt = f"""
You are a YouTube content repurposing expert.

Based on this transcript generate:

1. Short summary
2. 10 viral hooks
3. LinkedIn post
4. Twitter thread
5. Key bullet points
6. YouTube description
7. Blog outline
8. 7 day content distribution plan

Transcript:
{transcript[:12000]}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        result = response.choices[0].message.content

        return render_template_string(HTML, result=result)

    except TranscriptsDisabled:
        return render_template_string(HTML, error="Transcripts are disabled for this video.")

    except NoTranscriptFound:
        return render_template_string(HTML, error="No transcript available for this video.")

    except VideoUnavailable:
        return render_template_string(HTML, error="Video unavailable.")

    except Exception as e:
        return render_template_string(HTML, error=str(e))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
