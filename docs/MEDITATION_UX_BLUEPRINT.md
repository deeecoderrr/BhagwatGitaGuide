# Guided Meditation UX Blueprint (Web + Mobile)

Last updated: 2026-04-27

## Why this exists

This document captures the planned product/UX flow for a dedicated guided
meditation section so future AI sessions can continue implementation without
re-discovering intent from chat history.

The meditation experience should be clearly separate from ask/chat while still
feeding the core guidance loop.

## Product identity and positioning

- Ask flow = "Get guidance for my situation now."
- Meditation flow = "Practice now and regulate state."
- Reader flow = "Study scripture in depth."

Do not merge meditation controls into the active chat thread surface.
Keep meditation as a parallel primary flow with explicit entry points.

## Session structure (30 minutes canonical)

Current user-intended structure is 28 minutes. To make a true 30-minute guided
session, use:

1. Settling and intention - 1 min
2. Pranayam - 7 min
3. Gentle yoga - 8 min
4. Mantra chanting - 5 min
5. Affirmation - 2 min
6. Living the mantra reflection - 4 min
7. Bhakti/devotion rise - 2 min
8. Closing gratitude/silence - 1 min

Total = 30 min

## Information architecture

## Entry points

- Web: top nav item `Meditate` or `Daily Sadhana`
- Mobile: dedicated tab `Meditate`
- Optional contextual CTA from chat completion: "Practice 30-min session"

## Core screens

1. Meditation home
2. Session setup (optional in v1)
3. In-session player (single immersive screen)
4. Session complete (reflection + bridge back to chat)
5. History/streak (v2)

## UX flow (MVP)

1. User opens `Meditate`
2. Sees primary card: `30-min Guided Sadhana`
3. Taps `Start Session`
4. Player runs through timed segments with clear transitions
5. Completion screen asks mood check + one-line intention
6. CTA to ask/apply in chat:
   - "Apply this to my current situation"
   - deep link into ask screen with prefill

## Web UX spec

## Meditation home

- Hero title: "30-minute guided sadhana"
- Subtitle: calm practical value, not medical claims
- Segment chips row:
  - Pranayam 7m
  - Yoga 8m
  - Chanting 5m
  - Affirmation 2m
  - Living the mantra 4m
  - Bhakti 2m
- CTA: `Start Session`
- Secondary CTA: `10-min quick reset` (if enabled)

## In-session player

- Full-height focused panel
- Header:
  - elapsed and remaining time
  - current phase label
- Middle:
  - phase instructions (short lines)
  - optional Sanskrit/Hindi line where relevant
  - optional visual cue (breathing orb / posture icon)
- Bottom:
  - segmented progress bar for all phases
  - controls: Pause, Resume, Next, Exit
- Minimal distraction:
  - no conversation list
  - no dense sidebars

## Completion screen

- Success state + streak count
- 1-tap mood check:
  - Calmer
  - Same
  - Distracted
- Journal prompt:
  - "One intention you will carry today"
- CTA group:
  - `Apply in guidance chat`
  - `View today's verse`

## Mobile UX spec (Expo)

## Tab and routing

- New tab route: `/(tabs)/meditate`
- Session player route: `/meditate/session/[id]` or `/meditate/session`
- Completion route: `/meditate/complete`

## Mobile meditation home

- Large start card with single dominant CTA
- Segment breakdown as compact list
- Optional download/offline badge for future

## Mobile in-session player

- Top safe area:
  - back/exit
  - countdown
- Center:
  - instructions + optional visual cue
- Bottom sticky controls:
  - pause/resume
  - skip phase (optional if allowed)
- Haptic cues on phase transitions

## Mobile completion

- mood chips
- short text reflection field
- CTA to open ask flow with prefilled prompt

## Cross-flow integration with current product

## Chat -> Meditation

- Add non-intrusive CTA after emotionally intense guidance:
  - "Take a 30-minute guided practice"

## Meditation -> Chat

- Completion CTA prefill examples:
  - "I finished the 30-minute session. Help me apply this calm in [work/relationship]."
  - "I noticed anxiety during pranayam. Give me a Gita-grounded next step."

## Reader -> Meditation

- Optional from verse detail:
  - "Practice this teaching now"

## Visual direction constraints

Keep aligned with current sacred-futuristic system:

- Palette: midnight, gold, soft violet/sea
- Motion: slow, meaningful, non-noisy
- Typography: sacred headline + high-legibility body
- Avoid:
  - fitness app look
  - crypto/trading neon
  - crowded dashboard density

## Audio and guidance behavior

- Voice track per phase (v1 can be single stitched track with timed markers)
- Transition bell/chime at phase boundary
- Respect reduced-motion and low-stimulation preferences
- Keep instruction copy short and slow-paced

## Data model/API plan (proposed, not implemented)

Potential entities:

- MeditationProgram
  - id, slug, title, language, total_seconds, is_active
- MeditationPhase
  - program_id, order, title, duration_seconds, instruction_text
- MeditationSessionLog
  - user_id, program_id, started_at, completed_at, completion_pct
- MeditationCheckIn
  - session_id, mood, note

Potential API endpoints:

- GET `/api/meditation/programs/`
- GET `/api/meditation/programs/<slug>/`
- POST `/api/meditation/sessions/start/`
- POST `/api/meditation/sessions/<id>/complete/`
- POST `/api/meditation/sessions/<id>/checkin/`

## MVP implementation sequence

1. Web meditation home + static 30-min configuration
2. Mobile meditation tab + in-session timer
3. Completion check-in + deep link to chat prefill
4. Persist session logs and streak signal

## Success metrics (first pass)

- Session starts/day
- Session completion rate
- Completion -> chat continuation rate
- 7-day repeat practice rate

## Notes for future AI agents

- Preserve separation between ask flow and practice flow.
- Keep the 30-minute structure explicit and editable in one config source.
- Reuse existing theme tokens (`gita-app-theme.css` and mobile `theme.ts`).
- If implementing UI changes, also update:
  - `docs/USER_GUIDE.md`
  - `docs/DEVELOPER_GUIDE.md`
  - `PROGRESS.md`
