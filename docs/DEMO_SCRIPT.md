# Demo Video Script — Multimodal Traffic Intelligence Platform

**Target length:** 60–75 seconds
**Format:** 1080p / 30 fps / MP4 / no intro jingle / optional synth bed at -24 dB
**Audience:** Leonardo SpA, Capgemini Engineering, Italian municipalities, EU smart-city startups, ADAS companies
**Tone:** confident, engineer-to-engineer, no marketing fluff
**Audio:** optional voiceover in English; if none, burn large-font captions on-screen (recruiters often watch muted on phones)

---

## Rule of thumb

Every 5 seconds must answer one of: **what is it · does it work · can I run it**. Cut anything else.

---

## Shot-by-shot (75-second target)

### Shot 1 · 0:00–0:04 — Cold open (hook)
**Video:** Full-screen dashboard playing live detections on highway footage. Bounding boxes rendering, metrics ticking, plate numbers popping in.
**Caption (bottom, large):** `Real-time traffic intelligence. 12–15 FPS on a laptop CPU.`
**Voice (optional):** *"This is a traffic intelligence platform running entirely on my laptop."*

> **Why:** Lead with the working product. No logo, no title card. The first second must prove "this is real."

---

### Shot 2 · 0:04–0:12 — Problem framing
**Video:** Split screen or hard cut:
- Left: a wall of raw RTSP feeds (screen grab of 4-6 thumbnail cameras, use any stock wall-of-cameras footage you can find royalty-free, or a mock-up still).
- Right: the same feeds, but with overlaid detections + plate numbers + incident pins.
**Caption:** `Cameras everywhere. Answers nowhere.`
**Voice (optional):** *"Operators have hundreds of feeds. Most pipelines detect objects but lose identity, can't read plates, and surface events instead of insight."*

> **Why:** State the problem in one breath. Don't dwell.

---

### Shot 3 · 0:12–0:24 — Ingest demo (RTSP + YouTube)
**Video:** Screen recording of the React dashboard's **Add Source** panel:
1. Paste an RTSP URL → click → detections start within 2 seconds.
2. Cut. Paste a YouTube URL → click → detections start within 3 seconds.
3. Small pop-up chip shows `RTSP` then `YouTube` classifier badge.
**Caption:** `RTSP · YouTube · HTTP · file — one endpoint.`
**Voice (optional):** *"It takes RTSP, YouTube, HTTP, or uploaded video. Same pipeline, same UI."*

> **Why:** This is your differentiator over every other "I trained YOLO on traffic" portfolio project. Show it fast.

---

### Shot 4 · 0:24–0:36 — The pipeline visualized
**Video:** Zoom into the dashboard's main canvas. Slow pan across the live feed showing:
- Bounding boxes (color-coded by class: car, truck, bus, motorcycle, bicycle, person)
- Track IDs floating above boxes (e.g. `#42`, `#43`)
- License plate text boxes popping in as OCR resolves (e.g. `FA123CD`)
- One incident pin lights up amber → `STOPPED VEHICLE · 14s`
**Caption (fade through):**
- `YOLOv8 detection`
- `DeepSORT tracking`
- `EasyOCR plates`
- `Incident heuristics`
**Voice (optional):** *"Six asyncio stages. Detection, tracking, plate OCR, and incident detection, all on the same frame stream."*

> **Why:** Prove technical depth. Show the labels fading in — recruiters scrub this part twice.

---

### Shot 5 · 0:36–0:48 — Metrics + dashboard polish
**Video:** Cut to the right-hand metrics panel:
- Total Objects counter ticking
- Recharts line graph filling in real-time (vehicles per minute)
- Bar chart populating (vehicle types)
- Active Tracks number fluctuating
**Caption:** `70–110 ms end-to-end latency. WebSocket at 15 FPS, 720p q60 JPEG.`
**Voice (optional):** *"Metrics broadcast every second, database writes batched every five, back-pressure cap of 100 frames. Production-safe defaults."*

> **Why:** Numbers beat adjectives. The latency line puts you in a different bucket than the other candidates.

---

### Shot 6 · 0:48–1:02 — Chat-over-data (the kill shot)
**Video:** Open the chat panel on the right. Type (or show pre-typed):
> *"How many trucks went through in the last 5 minutes, and were there any stopped vehicles?"*

Hit send. Response appears over ~3 seconds, streaming:
> *"In the last 5 minutes: 23 cars, 4 trucks, 1 bus. One stopped-vehicle incident at 14:23:07, lane 2, duration 14 seconds. Plate FA123CD."*

**Caption:** `Gemini 2.5 Flash grounded in live detection context.`
**Voice (optional):** *"And it answers natural-language questions grounded in the live detection data — not hallucinated."*

> **Why:** This is the "wait, really?" moment. Let it breathe — don't cut away.

---

### Shot 7 · 1:02–1:12 — Shipping story
**Video:** Terminal window. Type (slowly, realistically):
```
git clone https://github.com/Bharathkondur/...
cd Multimodal-Traffic-Intelligence-platform
docker compose up --build
```
Cut to Docker pulling images (speed up 4×), then to browser opening `localhost:3000` with the dashboard live.
**Caption:** `One command. Full stack. No GPU required.`
**Voice (optional):** *"Three commands. FastAPI, Postgres, Redis, Grafana, React — all wired."*

> **Why:** Recruiters at Capgemini-style SIs care *how you ship*. This is the proof.

---

### Shot 8 · 1:12–1:15 — Outro card
**Video:** Static card, dark navy background matching portfolio (#080c10), Space Mono + Syne fonts.
```
MULTIMODAL TRAFFIC INTELLIGENCE PLATFORM

bharathkondur.github.io
github.com/Bharathkondur/Multimodal-Traffic-Intelligence-platform

Bharath Kumar Kondur · CV / LLM Engineer
```
**Voice:** none. Silence lands harder.

---

## Pacing notes

- **First 10 seconds must hook.** If Shot 1 doesn't look impressive on mute, re-record the footage with better traffic.
- **Don't narrate everything.** Pick 2-3 places to speak. Let the captions carry the rest. Recruiters watch muted.
- **Cut aggressively.** If a shot is 3 seconds too long, cut it. Better to feel rushed than bored.
- **No zoom-bouncing.** One pan per shot, max.
- **Music is optional.** If you use it, low-fi synth or ambient pad at -24 dB. No drops, no drums.

---

## What to record (checklist before you hit "record")

Before firing up OBS, have all of this ready on the same machine:

- [ ] Stack running end-to-end: `docker compose up --build` succeeded, all services green.
- [ ] 3 good test inputs queued:
  - [ ] A downloaded highway clip with clear plates (30-60 seconds).
  - [ ] An RTSP URL that works (test with `ffplay rtsp://...` first). [Samples: http://www.insecam.org or a local IP camera.]
  - [ ] A YouTube URL of traffic footage (test `yt-dlp -g URL` resolves cleanly first).
- [ ] Chrome at 125% zoom, bookmarks bar hidden, no notifications visible, DND enabled.
- [ ] Dashboard pre-loaded at `http://localhost:3000`. Dark mode confirmed.
- [ ] Terminal: clean, large font (16-18 pt), dark theme, prompt shortened (`PS1='$ '`).
- [ ] Desktop wallpaper changed to solid dark navy (#080c10) to match brand.
- [ ] Cursor on the browser tab is the default pointer (custom cursor on the portfolio HTML page is fine, but screen-record the running app, not the portfolio).
- [ ] Webcam / mic off unless narrating.
- [ ] Test the chat prompt ahead of time — actually ask it the question and make sure the answer is accurate. Don't cut to "fake" answers.

---

## Two variants to record

**Variant A — Smart-city / Leonardo / municipalities**
Lead shot 1 with RTSP camera feed (not YouTube). Emphasize incident detection + plate reading. Cut shot 6 (chat) to 8 seconds. Total: 60 s.

**Variant B — ADAS / AV / engineering-led buyers**
Lead shot 1 with dashcam-style footage. Emphasize tracking persistence + latency numbers. Extend shot 5 (metrics) to 16 s. Cut shot 6 (chat) entirely. Total: 55 s.

Pick based on who you're sending the link to.

---

## Hero GIF (for GitHub README, derived from same footage)

Extract 8–10 seconds from **Shot 4** (pipeline visualized — boxes, tracks, plate overlays).

ffmpeg command lives in `docs/RECORDING_GUIDE.md`. Target: **<5 MB, 640–720px wide, 10-12 fps, looping.**

---

## Title + description for YouTube upload (unlisted)

**Title:** `Multimodal Traffic Intelligence Platform — real-time CV + LLM demo`

**Description:**
```
A real-time traffic intelligence platform: YOLOv8 detection, DeepSORT tracking,
EasyOCR plate recognition, incident detection, and an LLM chat interface
grounded in the live detection data.

Ingests RTSP, YouTube, HTTP, webcam, or uploaded video — same pipeline.
Runs on a laptop via `docker compose up`.

Project page: https://bharathkondur.github.io/projects/multimodal-traffic-intelligence.html
GitHub: https://github.com/Bharathkondur/Multimodal-Traffic-Intelligence-platform

Built by Bharath Kumar Kondur · https://bharathkondur.github.io
```

**Visibility:** Unlisted (so only people with the link see it — recruiters yes, public no).
**End screen:** none.
**Tags:** none (unlisted video, irrelevant).

---

## Final pre-flight (before publishing the link)

- [ ] Watch the whole video on mute. Does it still sell?
- [ ] Watch at 1.25× — any shot that drags, cut.
- [ ] Upload to YouTube as **unlisted**. Copy the `https://youtu.be/XXXX` link.
- [ ] Replace `TODO` in 3 places:
  - `README.md` (two links + one thumbnail URL)
  - `portfolio/multimodal-traffic-intelligence.html` (two CTA buttons + the placeholder click handler)
  - `docs/STRATEGY.md` if you referenced it
- [ ] Extract the hero GIF (see `RECORDING_GUIDE.md`), save to `docs/hero.gif`, reference from README.
- [ ] Push the commit. Reload the portfolio page. Verify both the embed and the GitHub link open cleanly.
