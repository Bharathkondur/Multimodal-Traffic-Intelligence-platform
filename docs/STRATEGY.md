# Portfolio Showcase Strategy — Multimodal Traffic Intelligence Platform

**Audience:** Recruiters and hiring managers at Leonardo SpA, Capgemini Engineering, Italian municipalities, EU smart-city startups, ADAS/AV companies.

**Goal:** Convert a 10-second portfolio scan into a 3-minute deep-dive, and a 3-minute deep-dive into an interview.

---

## The problem with hosting a live demo

Running this stack (YOLOv8 + EasyOCR + DeepSORT + Postgres + Redis + FastAPI + React) on a free tier (Railway, Fly, Render) means cold starts, GPU-less inference at 2-3 FPS, and frequent crashes. A recruiter clicking a dead link or watching detections stutter is worse than no demo at all.

**Rule:** every asset on the portfolio must look production-grade within 5 seconds. Broken demos actively disqualify.

---

## Three-layer funnel

The strategy is to give recruiters progressively more depth as their interest grows — with zero friction at each step.

### Layer 1: Portfolio grid card (10-second scan)
`https://bharathkondur.github.io/` — new 4th project card alongside Self-Correcting RAG, Energy LLM, TrackStreak.

- Title: **Multimodal Traffic Intelligence Platform**
- One-line pitch: *Real-time vehicle detection, tracking, ANPR, and incident alerts from any RTSP / YouTube / video source — with an LLM chat interface over the live data.*
- Tech chips: `YOLOv8` `DeepSORT` `EasyOCR` `FastAPI` `WebSocket` `LangGraph` `PostgreSQL` `Docker`
- CTA: **View project →** (links to Layer 2)

### Layer 2: Dedicated project page (60-second skim)
`https://bharathkondur.github.io/projects/multimodal-traffic-intelligence.html` — single HTML file matching the existing portfolio aesthetic (Space Mono + Syne, dark navy + blue/cyan, clip-path buttons, terminal cards).

Sections in scroll order:
1. Hero — title + 1-sentence pitch + primary CTAs (GitHub, Demo video)
2. **Embedded 60-second demo video** (YouTube unlisted) — this is the single highest-leverage asset
3. Problem → Solution → Impact (smart-city framing)
4. Architecture diagram (Mermaid + SVG fallback showing 6-stage async pipeline)
5. Tech stack chips
6. Feature list (detection, tracking, ANPR, incidents, LLM chat, live stream ingest)
7. Performance numbers (FPS, latency, throughput on laptop hardware)
8. **Try it locally** block — `git clone … && docker compose up` (3 lines, copy-pasteable)
9. Links: GitHub repo, demo video, back to portfolio

### Layer 3: GitHub repository (3-minute deep-dive)
`https://github.com/bharathkondur/multimodal-traffic-intelligence` (or whatever repo hosts this code).

- README hero GIF (auto-playing in the GitHub render, <5MB)
- Badges (Python version, license, Docker, last commit)
- 1-sentence pitch identical to portfolio
- 30-second YouTube demo link (same video as Layer 2)
- `docker compose up` quickstart — working in under 5 minutes on a fresh laptop
- Architecture Mermaid diagram
- Performance section with real numbers
- Feature list with screenshots
- Contribution / license / contact

### Layer 4 (optional): Cloud-hosted preview
Only if a target recruiter explicitly asks. A one-pager on Render with the YOLO pipeline disabled (static screenshots + pre-recorded WebSocket replay). This is a fallback, not the primary asset.

---

## Why the demo video is the center of gravity

A 60-75 second unlisted YouTube video (embedded on the portfolio page, linked from the README) gives recruiters the "is this real?" proof without the reliability cost of a live deployment. It:

- Plays instantly, no cold start
- Works on phones (recruiters screen candidates on mobile)
- Lets you control the narrative (good lighting, good plates, good traffic)
- Is cheap to remake if tech stack changes
- Doesn't leak an API key or Gemini quota

The GIF for the GitHub README comes from the same source footage — extract the best 8-10 second segment and ffmpeg it down to <5MB.

---

## Concrete deliverables (this branch)

| # | File | Purpose | Status |
|---|------|---------|--------|
| 6 | `docs/STRATEGY.md` | This document | ✅ |
| 7 | `portfolio/multimodal-traffic-intelligence.html` | Layer 2 project page | pending |
| 8 | `portfolio/project-card-snippet.html` | Drop-in 4th card for portfolio grid | pending |
| 9 | `README.md` (repo root) | GitHub README rewrite | pending |
| 10 | `docs/DEMO_SCRIPT.md` | 60-75s shot-by-shot video script | pending |
| 11 | `docs/RECORDING_GUIDE.md` | OBS + ffmpeg + YouTube upload guide | pending |

---

## Execution order (leverage-weighted)

1. **README.md** — the artifact a recruiter opening the GitHub link sees first. Ship this even before the video exists; link `TODO: video` placeholder.
2. **Project page + card snippet** — the artifacts the portfolio links to. Deployable immediately.
3. **Demo script + recording guide** — turn the recruiter-facing promises into a recorded video. 1-2 hours of work once the platform is running locally.
4. **Record the video** — follow the script with OBS, upload unlisted, embed on the portfolio page, generate GIF for README.
5. **Push to `bharathkondur.github.io`** — add the card to `index.html`, copy the project page into `projects/`.

Estimated time to all recruiter-ready: **1 afternoon** (if the Docker stack already works end-to-end).

---

## What not to do

- **Don't** host the full stack on a free tier. Dead links are net-negative.
- **Don't** record the demo until you have 3-4 good test videos (highway footage with clear plates) queued up locally. Recording takes 10 tries.
- **Don't** use stock traffic footage in the demo — recruiters can tell, and it suggests the platform doesn't actually work on real inputs.
- **Don't** write >2 paragraphs of prose on the project page. Recruiters skim. Lead with the video, then tech chips, then architecture, then quickstart.
- **Don't** put the LLM chat as the hero feature — it's impressive but it's a wrapper. The differentiator for smart-city recruiters is *real-time multi-stream ANPR with incident detection*. Lead with that.

---

## Positioning for target companies

| Company type | Lead with | De-emphasize |
|---|---|---|
| **Leonardo SpA** (defence / aerospace / surveillance) | Real-time stream processing, multi-source fusion, robustness to degraded RTSP | LLM chat |
| **Capgemini Engineering** (SI / delivery) | Production architecture, Docker Compose, DB migrations, WebSocket protocol design | Novelty |
| **Italian municipalities / smart-city** | ANPR accuracy, incident detection, dashboard UX, multilingual plate support roadmap | Hardware specifics |
| **EU smart-city startups** | Cost per stream, horizontal scale story, LLM chat-over-data as analytics differentiator | Everything defence |
| **ADAS / AV companies** | Tracking (DeepSORT), latency numbers, sensor fusion roadmap | Chat / dashboards |

Tailor the LinkedIn message you send with the link accordingly — don't send the same pitch to Leonardo and a smart-city startup.
