import os
import re
import tempfile
import subprocess
from flask import Flask, request, render_template_string
from openai import OpenAI

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

def download_audio(youtube_url: str) -> str:
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

    command = [
        "yt-dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        "--no-playlist",
        "-o", output_template,
        youtube_url,
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Audio download failed: {result.stderr.strip() or result.stdout.strip() or 'Unknown yt-dlp error'}")

    for filename in os.listdir(temp_dir):
        if filename.endswith((".m4a", ".webm", ".mp4", ".mp3", ".wav", ".mpeg", ".mpga", ".ogg", ".flac")):
            return os.path.join(temp_dir, filename)

    raise RuntimeError("Audio file was not created.")

def transcribe_audio(audio_path: str) -> str:
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file,
        )
    return transcript.text

@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML, result=None, error=None, youtube_url="")

@app.route("/generate", methods=["POST"])
def generate():
    youtube_url = request.form.get("youtube_url", "").strip()

    try:
        get_video_id(youtube_url)
        audio_path = download_audio(youtube_url)
        transcript = transcribe_audio(audio_path)

        if not transcript or len(transcript.strip()) < 50:
            raise RuntimeError("Transcript was too short or unavailable.")

        prompt = f"""
You are a YouTube content repurposing expert.

You are an expert YouTube growth strategist.

Analyze the transcript below and generate a Creator Growth Pack.

The goal is to help a business YouTuber turn one long video into many pieces of high-performing content.

Generate exactly the following:

10 VIRAL HOOKS  
Short opening lines designed to capture attention in the first 3 seconds of a video.

10 SHORT-FORM VIDEO IDEAS  
Ideas for TikTok / YouTube Shorts / Reels extracted from the main video.

5 YOUTUBE TITLES  
High click-through rate titles optimized for YouTube.

3 TWITTER THREAD IDEAS  
Each thread should contain 4–5 tweets summarizing useful ideas.

2 LINKEDIN POSTS  
Professional style posts suitable for business creators.

Write clearly and avoid generic advice.  
Focus on strong angles, curiosity, and shareable ideas.

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

    except Exception as e:
        return render_template_string(
            HTML,
            result=None,
            error=f"DEBUG ERROR: {str(e)}",
            youtube_url=youtube_url,
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
