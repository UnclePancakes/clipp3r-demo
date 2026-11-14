# CLIPP3R Demo
> A demo version of the CLIPP3R video clipping software.

# 🎬 ai-clips-maker  
> **Created by Alperen Sümeroğlu** — An AI-assisted video library for turning long-form content into short clips.

`ai-clips-maker` is a modular Python library for **creators, educators, and developers**. It transcribes speech, suggests topical time ranges, adds readable captions, and exports portrait video with face-guided framing.

---

## 📚 Contents  
- [📦 Features](#-features)  
- [🛠 Installation](#-installation)  
- [🚀 Quickstart](#-quickstart)  
- [🔍 How It Works](#-how-it-works)  
- [⚙️ Tech Stack](#-tech-stack)  
- [🎯 Use Cases](#-use-cases)  
- [🧪 Tests](#-tests)  
- [🗺 Roadmap](#-roadmap)  
- [🤝 Contribute](#-contribute)  
- [👤 Author](#-author)  
- [🎧 Weekly Rewind Podcast](#-weekly-rewind-podcast)  
- [📄 License](#-license)

---

## 📦 Features  
- 🎞️ Suggest topical segments based on speech  
- 🧠 Speech transcription with word-level timestamps using Faster-Whisper
- 💬 Burned-in, word-timed captions with high-contrast styling  
- 🪄 Face-aware framing over a blurred vertical background  
- 🗣️ Optional speaker diarization (who spoke when) via Pyannote  
- 📐 Crop metadata for 9:16 (vertical), 1:1 (square), and 16:9 (wide) formats  
- 🔌 Modular and easily extensible pipeline

---

## 🛠 Installation  

```bash
# From the project directory
python -m pip install -e .
```

Install the optional speaker-aware resizing dependencies with
`python -m pip install -e ".[resize]"` if you need the `resize` API. The CLI's
face-aware framing requires OpenCV; install it with
`python -m pip install -e ".[framing]"`.

Install FFmpeg separately and ensure `ffmpeg` is on `PATH`. Use a Python 3.10+
environment; PyTorch, WhisperX, Faster-Whisper, and the pretrained models used
by the pipeline require substantial disk space and may take time to download.
Speaker diarization also requires a Hugging Face token with access to the
pyannote speaker-diarization model. The batch CLI uses Faster-Whisper's bundled
VAD and word timestamps; character timestamps are interpolated within each
word to limit memory use on long videos. The CLI does not need that token.

---

## 🚀 Quickstart  

```python
from ai_clips_maker import ClipFinder, Transcriber

# Transcribe an audio/video file and suggest topical segments.
transcriber = Transcriber()
transcription = transcriber.transcribe(audio_path="/path/to/video.mp4")
clips = ClipFinder(min_clip_duration=15, max_clip_duration=60).find_clips(
    transcription
)

for clip in clips:
    print(clip.begin_sec, clip.finish_sec)
```

Launch the CLIPP3R local web studio with:

```bash
python -m ai_clips_maker.webapp
```

Open `http://127.0.0.1:8787`. CLIPP3R accepts a public video URL supported by
yt-dlp or a local video upload. Sources and temporary job data are saved under
`~/Videos/CLIPP3R/`; set the `CLIPP3R_DATA_DIR` environment variable to change
that location. Final clips and each job's ZIP bundle are saved to
`~/Desktop/YouTube/CLIPS` by default. On the original Windows setup this
resolves to `C:\Users\<username>\Desktop\YouTube\CLIPS`. Set
`CLIPP3R_CLIPS_DIR` to override the final output folder. If a filename already
exists, CLIPP3R adds a collision suffix rather than overwriting it. The local
web server binds to localhost by default. Only fetch media you have permission
to use.

### Let friends try CLIPP3R

Share the repository with friends and have each person install and run CLIPP3R
on their own computer using the steps above. It is a local video-processing
app, not a GitHub Pages site or a hosted multi-user service: source videos and
exports stay on the computer running the app. Keep `CLIPP3R_HOST` at its
default `127.0.0.1`; do not expose the development server to the public
internet. Friends may set `CLIPP3R_CLIPS_DIR` to a writable folder on their
own computer.

After clips are ready, optionally select clips and choose **Suggest titles &
hashtags**. Provide audience, topic, creator goal, and tone once for the source,
then adjust that context per clip if needed. Suggestions are generated locally
from each selected clip's existing transcript and boundaries; CLIPP3R does not
send the clip or transcript to an external metadata service. The workflow
returns three title drafts, short rationales, a small set of relevant tags, and
visible uncertainty notes. Review and edit a draft, copy it, or skip it. Using a
title renames the clip file to that title (with an `.mp4` extension) and updates
the job ZIP. Filename-invalid characters are removed and existing names receive
a suffix. Metadata generation is optional and does not change clip creation;
CLIPP3R never publishes automatically. The local rule-based suggestions can
miss context, so check transcript accuracy, names, claims, and relevance before
using them. Short or apparently incomplete transcripts are flagged in the UI.

CLIPP3R combines topic-boundary candidates with transcript-aligned rolling
windows, so a quiet or loosely structured stream is less likely to produce only
one clip. The ranker looks for conversational hooks, pacing, and explicit
moment language such as donations, subscriptions, and chess tactics; it cannot
reliably detect visual-only events or guarantee that a moment is entertaining.
Up to 240 transcript-backed candidates are shown on a source timeline, with all
candidates selected initially. Search transcript snippets, sort by score or
timeline position, preview individual moments from the list or timeline, and
select the top 10 or 25 ranked moments before rendering. The review shows the
selected clip count and combined runtime. Candidate scores are editing signals,
not a prediction of virality. Upload progress occupies the first 10%;
transcription and selection follow, and multi-hour videos may take a long time.
Keep the page open while a large file is uploading. Once the server accepts a
job, refreshing the page reconnects to it without uploading the source again;
the job itself continues only while the local CLIPP3R server remains running.

The web studio lets you choose TikTok-style 1080 × 1920 portrait output or
preserve the source video's encoded dimensions and aspect ratio. First preview
the source video and review all proposed moments on a timeline, then render
your selection with captions and framing. After rendering, you can optionally
add or edit an on-screen headline and request title and hashtag suggestions
for selected clips. Headline edits update the rendered video and refresh the
ZIP; title selection renames the file and also refreshes the ZIP. You can
inspect the finished clip before downloading it.

The studio uses the locally bundled **Rubik 80s Fade** font for display
headings; its SIL Open Font License is included alongside the font. To use a
moving background, place a browser-compatible, optimized `wallpaper.webm` or
`wallpaper.mp4` in `ai_clips_maker/static/`. The page automatically enables it
and keeps a dark overlay for text contrast; people who prefer reduced motion
see the static background instead. The supplied `.mlw` wallpaper package is
not a standard browser video and cannot be decoded by FFmpeg. Export a web
video from the wallpaper provider's official app or obtain a web-compatible
source before adding it. Do not commit the original package as a substitute.

TikTok-style output keeps the full source frame centered over a blurred fill.
The **Creator pop** preset uses bold all-caps captions with karaoke color
emphasis and a vivid pink headline panel. Choose **Classic** to retain the
earlier caption and headline treatment. Before processing, you can enter an
optional streamer tag and explicitly choose Twitch or Kick to place its
supplied transparent platform logo beside the name. The tag is white with a
thick black outline and no colored name panel. CLIPP3R does not infer the
streamer's brand; choose the correct platform yourself, or leave the logo
unset. Headline and tag overlays are burned into the exported clip and cannot
be removed afterward. Word-timed captions have a subtle, semi-transparent
black panel for readability.
Original-dimension output requires even source dimensions for
broadly-compatible H.264 MP4 encoding.

Choose automatic language detection or a supported transcription language.
Afrikaans is explicitly supported by the installed Faster-Whisper backend and
uses the stronger `small` model when selected.
isiZulu, isiXhosa, Sepedi, Setswana, Sesotho, Xitsonga, siSwati, Tshivenda, and
isiNdebele are shown as unavailable rather than passed to a model that does not
support them. Automatic detection is best-effort and may not identify these
languages reliably; review generated transcripts and captions before posting.

To create captioned 9:16 videos from a local source with the CLI, use:

```bash
python -m ai_clips_maker /path/to/video.mp4 --max-duration 60
```

Use `--output-mode original` to preserve source dimensions and aspect ratio;
the default `tiktok` mode retains the 1080 × 1920 portrait layout. Pass
`--language af` to explicitly transcribe Afrikaans, or omit `--language` for
automatic detection.

Clips are written to a sibling `<video-name>_clips` folder, or to the path
passed with `--output`. The exporter preserves the entire source frame as a
centered landscape video over a portrait-filling blurred background. Detected
faces guide the background's horizontal framing; use `--no-face-tracking` to
keep it centered. Word-timed captions are burned in with bold Arial, a thick
dark outline, active-word highlighting, a subtle semi-transparent black
background panel, and margins that keep text away from screen edges and common
interface overlays.

This face-tracking mode follows the most prominent detected face; it does not
identify which person is speaking. Pyannote speaker diarization is a separate
optional feature and requires a Hugging Face token with access to its model.

The layout and safe margins follow TikTok's [creative best
practices](https://ads.tiktok.com/resources/help/article/creative-best-practices?lang=en),
which recommend 9:16 video, visible content within the UI safe zone, and
captions or text overlays. Caption contrast and heavy strokes are informed by
the [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

---

## 🔍 How It Works  
1. 🎧 Transcribes speech and adds word timestamps  
2. ✍️ Suggests and ranks non-duplicate topical clips up to 60 seconds  
3. 🙂 Tracks faces to guide the blurred portrait background  
4. 💬 Burns readable, word-timed captions into each clip  
5. 📤 Exports H.264/AAC MP4s with FFmpeg  

---

## ⚙️ Tech Stack  

| 🔧 Module         | 🧠 Technology                                     | 💡 Purpose                                              |
|------------------|---------------------------------------------------|----------------------------------------------------------|
| Transcription     | [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) | Speech-to-text with word timestamps |
| Diarization       | [Pyannote.audio](https://github.com/pyannote/pyannote-audio) | Speaker segmentation (who spoke when)              |
| Video Processing  | [OpenCV](https://opencv.org/), [PyAV](https://github.com/PyAV-Org/PyAV) | Frame-by-frame video control        |
| Scene Detection   | [Scenedetect](https://github.com/Breakthrough/PySceneDetect) | Detects shot boundaries                                 |
| ML Inference      | [PyTorch](https://pytorch.org/)                  | Powering WhisperX & Pyannote models                     |
| Data Handling     | [NumPy](https://numpy.org/), [Pandas](https://pandas.pydata.org/) | Transcription & clip structuring              |
| Media Utilities   | [ffmpeg](https://ffmpeg.org/), [libmagic](https://linux.die.net/man/3/libmagic) | Media decoding + type detection      |
| Testing Framework | [pytest](https://docs.pytest.org/)              | End-to-end and unit testing support                     |

> All tools were selected for speed, flexibility, and production-grade stability.

---

## 🎯 Use Cases  
- 🎙 **Podcasters** clipping episodes into shareable highlights  
- 📚 **Teachers** summarizing lecture content  
- 📱 **Social media teams** repurposing YouTube for Reels  
- 🧠 **Developers** automating video workflows  
- 🚀 **Startups** building AI-based content tools

---

## 🧪 Tests  

```bash
# Run test suite
pytest tests/
```

> Covers all components: transcriber, diarizer, clip detector, resizer.

---

## 🗺 Roadmap  

| Status | Feature                                            | Note                         |
|--------|----------------------------------------------------|------------------------------|
| ✅     | Core pipeline: Transcribe → Diarize → Detect       | Implemented in v1.0          |
| ✅     | Speaker-aware video cropping                       | Production ready             |
| 🚧     | Multi-language subtitle generation                 | Planned for Q2 2025          |
| 📌     | Auto-caption overlay                               | In design phase              |
| 🧪     | Web UI (upload + preview clips)                    | Prototype in progress        |
| 🧠     | HuggingFace or Streamlit live demo                 | On backlog                   |

---

## 🤝 Contribute  

We welcome pull requests, ideas, and feedback.

```bash
# Fork the repo
git clone https://github.com/alperensumeroglu/ai-clips-maker.git
cd ai-clips-maker

# Create feature branch
git checkout -b feat/your-feature

# Make changes, commit, and push
git commit -am "Add feature"
git push origin feat/your-feature
```

Before contributing, please review open issues and coding style guide.

---

## 👤 Author  

**Alperen Sümeroğlu**  
Computer Engineer • Entrepreneur • World Explorer 🌍  
15+ European countries explored ✈️

- 🔗 [LinkedIn](https://www.linkedin.com/in/alperensumeroglu/)  
- 🧠 [LeetCode](https://leetcode.com/u/alperensumeroglu/)  
- 🚀 [Daily.dev](https://app.daily.dev/alperensumeroglu)  

> *“Let your code tell your story — clean, powerful, and useful.”*

---

## 🎧 Weekly Rewind Podcast  

🎤 Weekly insights on AI, tech, and building globally — by Alperen Sümeroğlu.

> 🚀 What does it take to grow as a Computer Engineering student, build projects, and explore global innovation?

This API is part of a bigger journey I share in **Weekly Rewind** — my real-time documentary **podcast series**, where I reflect weekly on coding breakthroughs, innovation insights, startup stories, and lessons from around the world.

### 💡 What is Weekly Rewind?
A behind-the-scenes look at real-world experiences, global insights, and hands-on learning. Each episode includes:

- 🔹 Inside My Coding & Engineering Projects  
- 🔹 Startup Ideas & Entrepreneurial Lessons  
- 🔹 Trends in Tech & AI  
- 🔹 Innovation from 15+ Countries  
- 🔹 Guest Conversations with Builders & Engineers  
- 🔹 Productivity, Learning & Growth Strategies  

**🎧 Listen now:**  
- [Spotify](https://open.spotify.com/show/3Lc5ofiXh93wYI8Sx7MFCK)  
- [YouTube](https://www.youtube.com/playlist?list=PLSN_hxkfsxbbd_qD87kn1SVvnR41IbuGc)  
- [Medium](https://medium.com/@alperensumeroglu)  
- [LinkedIn](https://www.linkedin.com/company/weekly-rewind-tech-ai-entrepreneurship-podcast/)  

> *“True learning isn’t in tutorials — it’s in building, exploring, and reflecting.”*

---

## 📄 License  

MIT License — Free for commercial and personal use.  
© 2024 Alperen Sümeroğlu
