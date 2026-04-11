# Design Playbook

This document helps AI coding agents choose a fitting UI direction before
editing the frontend. It is especially important for automated redesign or UX
polish requests.

## Core Principle

Do not redesign this project like a generic AI product. Infer the product's
purpose first, then align every visual decision with that purpose.

For this repository, the product identity is:

- Bhagavad Gita guidance experience
- seeker-to-guide conversational flow
- emotionally calming and spiritually reflective
- sacred, luminous, and reassuring rather than clinical or corporate

## Redesign Workflow

Before substantial frontend edits:

1. Inspect routes, templates, copy, models, and user flows.
2. Infer the app purpose, user mindset, and key interaction loops.
3. Choose a theme name and visual direction.
4. Define or refine design tokens before scattered style edits.
5. Apply changes across layout, hierarchy, states, motion, and responsiveness.
6. Verify the redesign still supports readability and performance.

## Theme Mapping

### Spiritual guidance app

Use when the product is centered on contemplation, emotional grounding,
guidance, or devotion.

Recommended traits:

- warm celestial gradients
- soft gold, saffron, moonlight, deep blue, or devotional ivory accents
- gentle glow effects
- serene cards and panels
- spacious breathing room
- emotionally calming transitions

Avoid:

- hard-edged enterprise dashboard visuals
- flashy multi-color neon overload
- crowded layouts
- excessive glassmorphism that hurts readability

### Productivity or admin UI

If future sub-tools are added for internal management, keep those sections more
compact and utilitarian, but do not let that style dominate the seeker-facing
experience.

## Color System Guidance

Use a structured token system where possible:

- background
- surface
- surface-elevated
- text-primary
- text-secondary
- accent-primary
- accent-soft
- border-soft
- glow
- danger / success / warning

For this app:

- favor spiritual warmth and depth over sterile grayscale
- maintain strong contrast for body text
- use glow as emphasis, not as a constant everywhere

## Typography Guidance

- Pair one expressive display face with one readable body face when feasible.
- Headlines may feel sacred, elevated, or poetic, but body copy must remain
  easy to scan.
- Avoid default-looking typography when redesigning major user-facing sections.
- Keep long-form guidance text highly legible with comfortable line height.

## Motion Guidance

Motion should communicate presence, reverence, and clarity.

Use:

- soft reveals
- subtle hovering or floating accents
- meaningful loading states
- glow pulses for sacred or divine motifs

Avoid:

- aggressive bouncing
- distracting parallax overload
- constant motion in reading areas
- animation that competes with the guidance text

Suggested timing:

- short interaction transitions: `120ms` to `220ms`
- reveal or entrance transitions: `220ms` to `420ms`

## Imagery and Symbol Guidance

If using symbolic visuals, they should feel intentional and respectful.

Good motifs for this project:

- light rays
- aura glows
- subtle mandala geometry
- celestial gradients
- chakra-inspired circular motion
- devotional atmosphere

Use care with:

- literal deity depictions
- crowded religious collage imagery
- visuals that reduce sacred tone into novelty

## UX Priorities

Every redesign pass should try to improve:

- clarity of the current conversation state
- visibility of the active input and latest reply
- information hierarchy
- readability of long answers
- conversation navigation
- empty states and first-use onboarding
- responsiveness on mobile
- focus states and accessibility

## Chat-Specific Guidance

Because this app is conversation-first:

- the active thread should always feel visually grounded
- the latest message should be easy to locate
- thinking/loading states should feel spiritually aligned, not generic
- sidebar and global settings should feel secondary to the sacred dialogue
- verse references and Krishna-to-Arjuna framing should feel integrated, not
  bolted on

## Implementation Rules

- Prefer reusable CSS variables or shared style blocks over one-off inline
  styling.
- Keep visual choices cohesive across cards, forms, sidebars, buttons, and
  content sections.
- Preserve performance when adding animation libraries or effects.
- Do not change backend behavior unless the user asks for flow changes too.

## Final Summary Requirements

When a substantial UI redesign is completed, report:

- inferred purpose
- chosen visual direction
- UX issues improved
- reusable design-system updates
- files changed
