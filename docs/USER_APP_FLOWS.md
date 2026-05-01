# Mobile user app flows

**Purpose:** Diagrams for the **Expo app** (`bhagavadgitaguide_mobile-main`): auth, tabs, and how each major feature connects to routes and APIs. Mermaid renders in GitHub, many IDEs, and Notion.

**Code reference:** `expo/app/(tabs)/_layout.tsx` — bottom tabs are **Today**, **Ask**, **Meditate**, **History**, **Insights**; `read` and `profile` use `href: null` (reachable via navigation, not tab bar).

**Backend routes:** `/api/…` and `/api/v1/…` are equivalent (`config/urls.py`).

**Product note (Today screen):** Some shortcuts still point to **`/history`** (conversation threads). **Saved reflections library** is also reachable from Today (**`/saved-reflections`**) and from Profile (`expo/app/(tabs)/profile.tsx`).

---

## 1. Entry and authentication

```mermaid
flowchart TD
  A[App launch] --> V[Intro video — play or Skip]
  V --> B{Hydrate session}
  B -->|token in storage| C[Signed in user]
  B -->|guest flag, no token| D[Guest mode]
  B -->|nothing| E[/auth screen/]

  E --> F[Login]
  E --> G[Register]
  E --> H[Continue as guest]

  F --> I[POST /api/auth/login/ → token]
  G --> J[POST /api/auth/register/ → token]
  H --> D

  I --> K[(tabs)]
  J --> K
  C --> K
  D --> K

  K --> L[Today · Ask · Meditate · History · Insights]
```

---

## 2. Main shell (tabs + hidden routes)

```mermaid
flowchart LR
  subgraph Tabs["Bottom tabs"]
    T[Today]
    A[Ask]
    M[Meditate]
    H[History]
    I[Insights]
  end

  subgraph Hidden["Routable, not in tab bar"]
    R[Read library]
    P[Profile hub]
  end

  T -->|Navigate| R
  T -->|Navigate| P
  T -->|shortcuts| A
```

---

## 3. Today tab → downstream features

```mermaid
flowchart TD
  Today[Today tab]

  Today --> DV[Daily verse card — tap verse]
  Today --> LP[Long-press card → synthesis insight]
  DV --> Verse["/verse/ch.vrs"]
  Verse --> Note[Verse note API]
  Verse --> RO[reading/verse-open]

  Today --> AskTab["/ask shortcut"]
  Today --> ReadTab["/read library"]
  Today --> ProfileBtn["Header → /profile"]

  Today --> HistShortcut["Heart card → /history · chat threads"]
  Today --> SavedLib["Saved reflections tile → /saved-reflections"]
  Today --> MedShortcut["Meditation row → /meditate"]

  Today --> NH[Naam japa section]
  Today --> CH[Community preview]
  CH --> CommFull["/community"]

  ProfileBtn --> Profile["/profile"]
  Profile --> Saved["Saved reflections list + tap → /saved-reflection/id"]
  Profile --> Acct["/account"]
  Profile --> Notif["/notifications"]
  Profile --> Plans["/plans"]
  Profile --> PayHist["/payments"]
  Profile --> QA["/quote-art"]
  Profile --> Support["/support"]
  Profile --> HistAgain["/(tabs)/history"]
```

---

## 4. Ask (guidance Q&A)

```mermaid
flowchart TD
  Ask[Ask tab]

  Ask --> AuthBranch{User type}
  AuthBranch -->|Guest| GA["POST /api/v1/guest/ask/"]
  AuthBranch -->|Signed in| SA["POST /api/v1/ask/"]

  GA --> GH["guest/history"]
  SA --> Conv["conversations + messages"]

  Ask --> Thread[Pick / create conversation]
  Thread --> Msg["GET …/conversations/id/messages/"]

  Ask --> SaveRef["POST /api/saved-reflections/"]
  Ask --> FB["POST /api/v1/feedback/"]

  Msg --> Deep["/conversation/id deep link"]
  Deep --> SA
```

---

## 5. Read (library and search)

```mermaid
flowchart TD
  Read[Read screen]

  Read --> ChList["GET /api/chapters/"]
  ChList --> ChDetail["/chapter/n"]
  ChDetail --> VerseRow[Tap verse]
  VerseRow --> Verse["/verse/ref"]

  Read --> Search["GET /api/v1/verses/search/"]
  Search --> Verse
```

---

## 6. History (threads)

```mermaid
flowchart TD
  Hist[History tab]

  Hist --> List["GET /api/v1/conversations/"]
  List --> Open["/conversation/id"]
  Open --> Msgs["GET …/messages/"]
  Open --> Continue["POST /api/v1/ask/ with conversation"]

  List --> Del["DELETE …/conversations/id/"]
```

---

## 7. Insights

```mermaid
flowchart TD
  Ins[Insights tab]
  Ins --> API["GET /api/v1/insights/me/"]
  API --> Show[Engagement + journey aggregates]
```

---

## 8. Meditate (workflows and logging)

```mermaid
flowchart TD
  Med[Meditate tab]

  Med --> WF["GET /api/v1/practice/workflows/"]
  WF --> Detail["/practice/slug"]
  Detail --> Pay{Locked?}
  Pay -->|Purchase| CO["payments/create-order → verify"]
  Pay -->|Open| Play[Steps / playback UI]

  Med --> MS["POST …/practice/meditation-sessions/"]
  Med --> PL["POST …/practice/log/"]
  PL --> Types[japa_rounds / meditation_minutes / read_minutes]
```

---

## 9. Sadhana (guided programs)

Primary entry in app: **Meditate tab** → “Guided sadhana programs” → **`/sadhana`**.

```mermaid
flowchart TD
  Entry[Meditate tab → /sadhana]

  Entry --> ProgList["GET /api/v1/sadhana/programs/"]
  ProgList --> ProgDetail["/sadhana/slug"]
  ProgDetail --> Day["/sadhana/slug/day/n"]
  Day --> Steps[Step players + media]
```

---

## 10. Japa (personal commitments)

```mermaid
flowchart TD
  JapaEntry["/japa or /japa/new"]

  JapaEntry --> List["GET /api/v1/japa/commitments/"]
  List --> New["POST …/japa/commitments/"]
  List --> Detail["/japa/id"]

  Detail --> Start["sessions/start"]
  Detail --> Pause["sessions/id/pause"]
  Detail --> Resume["resume"]
  Detail --> Finish["finish-day"]
  Detail --> Fulfill["fulfill commitment"]
```

---

## 11. Plans and payments

```mermaid
flowchart TD
  Plans["/plans"]

  Plans --> Cat["GET /api/v1/plans/catalog/"]
  Plans --> Sub["GET /api/v1/subscription/status/"]
  Plans --> Ord["POST …/payments/create-order/"]
  Ord --> Bridge["Web checkout / Razorpay"]
  Bridge --> CB["/payments/callback"]
  CB --> Ver["POST …/payments/verify/"]
  Ver --> Hist["payments/history"]
```

---

## 12. Notifications and push

```mermaid
flowchart TD
  N["/notifications"]

  N --> Prefs["GET/PATCH …/notifications/preferences/"]
  N --> Dev["GET /api/v1/devices/"]
  N --> Reg["POST …/devices/register/ Expo token"]
  N --> Del["DELETE …/devices/id/"]

  Push[System push tap] --> Route["Deep link /verse/ref"]
```

---

## 13. Community and support

```mermaid
flowchart TD
  Comm["/community"]
  Comm --> List["GET /api/community/posts/"]
  Comm --> Post["POST … posts (auth)"]

  Sup["/support"]
  Sup --> Tickets["GET …/support/tickets/"]
  Sup --> New["POST …/support/"]
```

---

## 14. Quote art

Stack screen **`/quote-art`** (opened from Profile). Uses **`GitaBrowseAPIPermission`**: browser-style access without a token is allowed; **token + Free plan** may receive **403** on quote-art JSON routes — typically **Plus/Pro** for in-app token calls.

```mermaid
flowchart TD
  QA["/quote-art"]
  QA --> Styles["GET …/quote-art/styles/"]
  QA --> Feat["GET …/quote-art/featured/"]
  QA --> Gen["POST …/quote-art/generate/"]
```

---

## 15. Saved reflection detail

```mermaid
flowchart TD
  SR["/saved-reflection/id"]
  SR --> Get["GET /api/saved-reflections/id/"]
  SR --> Del["DELETE …"]
```

---

## 16. Typical journey (qualitative)

```mermaid
journey
  title Typical signed-in seeker path
  section Open app
    See Today + daily verse: 5
    Tap Ask or Read: 4
  section Guidance
    Ask question → read answer → save reflection: 5
  section Practice
    Meditate tab → log session OR open Sadhana/Japa: 4
  section Stay engaged
    Insights + reminders + verse from push: 4
```

---

## Design notes

- **Primary loop:** **Today** → **Ask** or **Read** → **Verse** → optional save / log practice.
- **Secondary loop:** **Meditate** / **Sadhana** / **Japa** → **Insights** and reminders.
- **Account:** **Profile** (`/profile`) → **Plans**, **payments history**, **notifications**, **account**, **quote art**, **support**, **saved reflections**, shortcuts back to **History** tab.

---

## Possible follow-ups (product / doc)

- Rename or clarify Today’s Heart card if users confuse **chat history** with **saved reflections**.
- **`POST …/sadhana/.../complete/`** exists on the API for day completion; confirm whether mobile should call it after playback.
- Align client paths on **`/api/v1/`** consistently (today some screens use `/api/...` without `v1`; behavior is the same).

---

*Last aligned with Expo tab layout and routes: 2026-04-27 (revised for Today → history vs profile, Meditate entry points, quote art / saved reflection / payments).*
