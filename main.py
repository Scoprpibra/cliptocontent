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
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ClipToContent</title>
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f4f6fb;
      color: #111827;
    }
    .wrap {
      max-width: 960px;
      margin: 0 auto;
      padding: 48px 24px;
    }
    .card {
      background: white;
      border-radius: 16px;
      padding: 32px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.08);
    }
    h1 {
      margin: 0 0 8px 0;
      font-size: 42px;
    }
    .subtitle {
      color: #6b7280;
      margin-bottom: 28px;
      font-size: 18px;
    }
    form {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }
    input[type="text"] {
      flex: 1;
      min-width: 280px;
      padding: 14px 16px;
      border: 1px solid #d1d5db;
      border-radius: 10px;
      font-size: 16px;
    }
    button {
      padding: 14px 20px;
      border: none;
      border-radius: 10px;
      background: #22c55e;
      color: white;
      font-size: 16px;
      font-weight: bold;
      cursor: pointer;
    }
    button:hover {
      background: #16a34a;
    }
    .error {
      background: #fef2f2;
      color: #991b1b;
      border: 1px solid #fecaca;
      padding: 14px 16px;
      border-radius: 10px;
      margin-top: 16px;
      white-space: pre-wrap;
    }
    .results {
      margin-top: 24px;
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 20px;
    }
    .results pre {
      white-space: pre-wrap;
      font-family: Arial, sans-serif;
      line-height: 1.5;
      margin: 0;
    }
    .copy-btn {
      margin-top: 14px;
      background: #2563eb;
    }
    .copy-btn:hover {
      background: #1d4ed8;
    }
    .small {
      color: #6b7280;
      font-size: 14px;
      margin-top: 24px;
    }
  </style>
  <script>
    function copyResults() {
      const text = document.getElementById("results-text").innerText;
      navigator.clipboard.writeText(text);
      alert("Copied");
    }
  </script>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>ClipToContent</h1>
      <div class="subtitle">Turn 1 YouTube video into hooks, posts, threads, summaries, and a content plan.</div>

      <form method="POST" action="/generate">
        <input
          type="text"
          name="youtube_url"
          placeholder="Paste YouTube link here"
          value="{{ youtube_url or '' }}"
          required
        />
        <button type="submit">Generate</button>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}

      {% if result %}
        <div class="results">
          <h2>Content Pack</h2>
          <pre id="results-text">{{ result }}</pre>
          <button class="copy-btn" onclick="copyResults()">Copy All</button>
        </div>
      {% endif %}

      <div class="small">
        Best with public YouTube videos that have captions available.
      </div>
    </div>
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


def fetch_transcript_text(video_id: str) -> str:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try English manual transcript first
        try:
            transcript = transcript_list.find_transcript(["en"])
            return " ".join(chunk["text"] for chunk in transcript.fetch())
        except Exception:
            pass

        # Then try generated English transcript
        try:
            transcript = transcript_list.find_generated_transcript(["en"])
            return " ".join(chunk["text"] for chunk in transcript.fetch())
        except Exception:
            pass

        # Then try any transcript and translate if possible
        for transcript in transcript_list:
            try:
                if transcript.language_code == "en":
                    return " ".join(chunk["text"] for chunk in transcript.fetch())
                translated = transcript.translate("en")
                return " ".join(chunk["text"] for chunk in translated.fetch())
            except Exception:
                continue

        raise NoTranscriptFound(video_id, [], None)

    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        raise e
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
        transcript_text = fetch_transcript_text(video_id)

        if not transcript_text or len(transcript_text.strip()) < 50:
            raise RuntimeError("Transcript was too short or unavailable.")

        prompt = f"""
You are an expert content repurposing assistant for YouTube creators.

Based on the transcript below, create a high-quality content pack with these clearly labeled sections:

1. SHORT SUMMARY
2. 10 VIRAL HOOK IDEAS
3. LINKEDIN POST
4. X/TWITTER THREAD (5 tweets)
5. KEY BULLET POINTS
6. YOUTUBE DESCRIPTION
7. BLOG POST OUTLINE
8. 7-DAY CONTENT DISTRIBUTION PLAN

Write in a practical, creator-focused style.
Make the output polished and ready to use.

Transcript:
{transcript_text[:12000]}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        result = response.choices[0].message.content.strip()

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
    except Exception as e:
        return render_template_string(
            HTML,
            result=None,
            error=f"Error: {str(e)}",
            youtube_url=youtube_url,
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
