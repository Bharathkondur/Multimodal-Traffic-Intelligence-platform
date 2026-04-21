# Recording + GIF Guide — Windows / OBS / ffmpeg

Companion to `DEMO_SCRIPT.md`. This file tells you the *exact* settings to record, compress, and ship the demo video and GIF.

Platform target: **Windows 10/11.** Most commands work on macOS/Linux with trivial substitutions.

---

## 1. Install the tools (one-time, ~10 min)

| Tool | Why | Install |
|---|---|---|
| **OBS Studio** | Screen recorder | https://obsproject.com/ (official installer) |
| **ffmpeg** | Video + GIF compression | `winget install ffmpeg` (PowerShell, admin) — or download from https://ffmpeg.org/ and add to PATH |
| **gifski** (optional) | Higher-quality GIFs than ffmpeg | https://gif.ski/ or `cargo install gifski` |

Verify from PowerShell:

```powershell
obs --version        # OBS is usually run from the GUI; this just proves it's installed
ffmpeg -version
```

---

## 2. OBS settings (one-time)

Open OBS → **Settings** (bottom right) and apply:

### Video tab
| Setting | Value |
|---|---|
| Base (Canvas) Resolution | `1920×1080` |
| Output (Scaled) Resolution | `1920×1080` |
| Common FPS Values | `30` |

### Output tab → switch to **Advanced** mode
| Setting | Value |
|---|---|
| Recording Path | Somewhere easy (e.g. `C:\Users\bhara\Videos\demo-raw\`) |
| Recording Format | `mp4` (or `mkv` if you're worried about crashes, then remux) |
| Encoder | `NVIDIA NVENC H.264` if you have an Nvidia GPU, else `x264` |
| Rate Control | `CQP` (constant quality) |
| CQ Level | `18` (near-lossless; file will be large, that's fine for the raw) |
| Keyframe Interval | `2` |
| Preset | `Quality` (NVENC) or `veryfast` (x264) |
| Profile | `high` |

### Audio tab
| Setting | Value |
|---|---|
| Desktop Audio | `Disabled` unless you need narration |
| Mic/Aux | Select your mic if narrating, else `Disabled` |
| Sample Rate | `48 kHz` |

### Hotkeys tab (huge quality-of-life)
- `F9` → Start Recording
- `F10` → Stop Recording

> If you mess up a shot, just hit `F10`, `F9` again, and re-do that shot. You'll stitch clips together in post.

### Scenes
- Delete the default scene and create one called **Demo**.
- Add a **Display Capture** source pointing at your primary monitor.
- (Optional) Add a **Window Capture** source targeting Chrome specifically — cleaner, no taskbar.

---

## 3. Pre-recording checklist

Before you hit `F9`, run through this list. Skipping one = re-record.

- [ ] Docker stack running and healthy: `docker compose ps` all green, `localhost:3000` loads.
- [ ] Clear browser cache or use a fresh Chrome profile so no autocomplete shows past URLs.
- [ ] Hide the bookmarks bar (`Ctrl+Shift+B`).
- [ ] Enable Windows **Focus Assist** (Do Not Disturb) — Notifications off.
- [ ] Close Slack, Discord, email, Spotify, anything that could pop a toast.
- [ ] Close any terminal with personal paths / usernames in the prompt — use a shortened prompt: in PowerShell run `function prompt { "$ " }`.
- [ ] Set your terminal font size to 16-18 pt so it reads on a phone.
- [ ] Pre-load the 3 test inputs in a scratch file so you can copy-paste URLs without searching.
- [ ] Screen recording app (OBS) in a tray-minimized state so its window doesn't show in the capture.
- [ ] One dry-run of each shot, no recording. Actually run the commands and watch the dashboard respond. If the RTSP feed takes 10 seconds to start, you need to know that before the tape rolls.

---

## 4. Recording flow

1. `F9` → record shot 1 → `F10`. Watch it back. If bad, delete and retry.
2. Repeat per shot.
3. You'll end up with 8 clip files named like `2026-04-19 14-23-05.mp4`.

> **Don't edit inside OBS.** Do the record-by-shot approach and stitch in post.

---

## 5. Stitching shots together (ffmpeg, no editor needed)

Create a text file `concat.txt` listing your clips in order:

```
file 'shot-01.mp4'
file 'shot-02.mp4'
file 'shot-03.mp4'
file 'shot-04.mp4'
file 'shot-05.mp4'
file 'shot-06.mp4'
file 'shot-07.mp4'
file 'shot-08.mp4'
```

Then:

```powershell
ffmpeg -f concat -safe 0 -i concat.txt -c copy demo-raw.mp4
```

No re-encode, no quality loss. Sub-second operation.

If you want proper cuts, transitions, or captions overlaid: use **DaVinci Resolve** (free, 1 hr learning curve) or **CapCut** (faster, shallower). But captions baked into OBS scenes or added via HTML overlay before recording is faster.

---

## 6. Adding captions (no editor needed)

Option A — burn-in captions via ffmpeg drawtext (fast, ugly syntax):

```powershell
ffmpeg -i demo-raw.mp4 -vf "drawtext=fontfile='C\:/Windows/Fonts/arial.ttf':text='Real-time traffic intelligence':fontcolor=white:fontsize=48:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-text_w)/2:y=h-120:enable='between(t,0,4)'" -c:a copy demo-captioned.mp4
```

Option B (recommended) — DaVinci Resolve, drag text layers, ~10 min once you know the UI.

---

## 7. Compress final video for YouTube upload

YouTube re-encodes anything, but uploading a lean file is faster:

```powershell
ffmpeg -i demo-raw.mp4 -c:v libx264 -crf 18 -preset slow -c:a aac -b:a 128k -movflags +faststart demo-final.mp4
```

Typical output: **20–40 MB** for 75 s of 1080p30.

Verify it's under 2 GB (YouTube's non-verified account limit) and plays back cleanly in VLC before uploading.

---

## 8. Upload to YouTube (unlisted)

1. Go to https://studio.youtube.com/ → **Create** → **Upload videos**.
2. Select `demo-final.mp4`.
3. Title + description: copy from `DEMO_SCRIPT.md` → "Title + description for YouTube upload" section.
4. **Visibility: Unlisted.** Not Private (private = only you can see it). Not Public (Public = spam crawlers).
5. No end screen, no cards, no ads.
6. Publish. Copy the shortlink (looks like `https://youtu.be/aB3xYz_p90k`).

---

## 9. Wire the YouTube link into the site

Run these find/replace operations across the repo:

**Files to edit:**
- `README.md`
- `portfolio/multimodal-traffic-intelligence.html`
- `docs/STRATEGY.md` (optional — just the layer-2 reference)

**Find:** `youtu.be/TODO`
**Replace with:** `youtu.be/aB3xYz_p90k` (your actual ID)

**Find:** `vi/TODO/maxresdefault` (README thumbnail)
**Replace with:** `vi/aB3xYz_p90k/maxresdefault`

For the portfolio HTML, replace the `<div class="video-placeholder">…</div>` block with the commented-out `<iframe>` right below it — and drop your video ID into the `src` URL. Example:

```html
<iframe src="https://www.youtube.com/embed/aB3xYz_p90k?rel=0"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowfullscreen></iframe>
```

Push the commit. Done.

---

## 10. Hero GIF for GitHub README

GitHub auto-plays GIFs in rendered README. Perfect for a hero frame.

### Step 1 — extract the source segment

Pick your best 8–10 seconds from the stitched `demo-raw.mp4`. Usually from Shot 4 (pipeline visualization).

```powershell
ffmpeg -ss 00:00:24 -i demo-raw.mp4 -t 10 -c copy gif-source.mp4
```

(`-ss 00:00:24` = start at 24 s, `-t 10` = take 10 s.)

### Step 2 — encode to GIF

**Option A — ffmpeg two-pass (reliable, decent quality):**

```powershell
# 1. Generate palette
ffmpeg -i gif-source.mp4 -vf "fps=12,scale=720:-1:flags=lanczos,palettegen" -y palette.png

# 2. Use palette
ffmpeg -i gif-source.mp4 -i palette.png -lavfi "fps=12,scale=720:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" -y docs/hero.gif
```

Typical output: **3–6 MB.** If over 5 MB:
- Lower `fps` to 10
- Lower `scale` to 640
- Shorten source to 8 seconds

**Option B — gifski (better quality, bigger file):**

```powershell
# First extract frames
ffmpeg -i gif-source.mp4 -vf "fps=12,scale=720:-1:flags=lanczos" frames/%04d.png

# Then encode
gifski --fps 12 --width 720 --quality 90 -o docs/hero.gif frames/*.png
```

### Step 3 — verify

```powershell
ls docs/hero.gif               # should be < 5 MB for fast GitHub rendering
```

Drop it into the README — the placeholder line is near the top:

```markdown
<img src="docs/dashboard-preview.svg" alt="Dashboard preview" width="100%">
```

Change to:

```markdown
<img src="docs/hero.gif" alt="Live demo" width="100%">
```

Commit, push, reload the repo on GitHub — the GIF auto-plays on the README page.

---

## 11. Optional: static screenshot fallback for slow connections

Recruiters on hotel wifi may see a broken GIF. Provide a static poster as fallback:

```powershell
ffmpeg -i gif-source.mp4 -ss 00:00:03 -vframes 1 -q:v 2 docs/hero-poster.jpg
```

Then use `<picture>` in HTML contexts (not possible in GitHub Markdown, but useful for the portfolio page):

```html
<picture>
  <source srcset="docs/hero.gif" type="image/gif" media="(min-width: 768px)">
  <img src="docs/hero-poster.jpg" alt="Live demo" width="100%">
</picture>
```

---

## 12. Final pre-publish checklist

- [ ] YouTube video uploaded as **unlisted**, link copied.
- [ ] `demo-final.mp4` backed up somewhere (Google Drive, local external) — source of truth if YouTube ever takes it down.
- [ ] `TODO` placeholders replaced in README + portfolio page.
- [ ] `docs/hero.gif` committed and under 5 MB.
- [ ] Opened the portfolio page in Chrome incognito — everything renders, video embed loads, GitHub link opens.
- [ ] Opened the GitHub repo in incognito — README GIF auto-plays, quickstart commands are copy-pasteable.
- [ ] Tested the portfolio link on a **phone** (send it to yourself via Slack/WhatsApp and tap). If the video doesn't play on mobile, fix before sharing.
- [ ] Sanity-checked that no secrets (API keys, passwords, internal hostnames) show in any recorded frame. Watch the video once with the mindset of a security reviewer.

---

## 13. Sharing the link

Paste into:

- LinkedIn profile → Featured section → "Add a link" → your portfolio URL (the portfolio page pulls the embed).
- LinkedIn posts → a 3-line teaser + the portfolio page link (not GitHub — higher conversion).
- Application cover letters → link the portfolio page, not the raw YouTube URL.
- Recruiter DMs → same; always route through the portfolio so you can update the video without breaking links.

---

## Troubleshooting

**"My GIF is 12 MB."**
Drop `fps` from 12 → 8, `scale` from 720 → 560. Shorten the clip. You rarely need more than 7 seconds of hero.

**"OBS is recording at 5 FPS."**
Your encoder is CPU-bound. Either (a) switch to NVENC if you have an Nvidia GPU, (b) drop canvas to 1280×720, or (c) record in 2-3 second shots so the buffer doesn't back up.

**"The video looks good on my 4K monitor but blurry on my phone."**
Record at 1920×1080 (not higher). YouTube's mobile transcoder handles 1080p beautifully; 4K gets crushed.

**"I don't know which footage to use for the demo."**
Search YouTube for "free traffic footage 1080p" or "highway dashcam royalty free." Download with `yt-dlp -f best <url>`. Or film your own through a window. Goal: 30-60 seconds of clear, plate-readable daylight footage.

**"ffmpeg isn't found on PATH."**
```powershell
winget install ffmpeg
# restart PowerShell
ffmpeg -version
```
