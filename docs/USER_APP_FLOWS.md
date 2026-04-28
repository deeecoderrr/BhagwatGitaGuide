# Mobile user app flows

**Purpose:** Diagrams for the **Expo app** (`bhagavadgitaguide_mobile-main`): auth, tabs, and how each major feature connects to routes and APIs. Mermaid renders in GitHub, many IDEs, and Notion.

**Code reference:** `expo/app/(tabs)/_layout.tsx` — bottom tabs are **Today**, **Ask**, **Meditate**, **History**, **Insights**; `read` and `profile` use `href: null` (reachable via navigation, not tab bar).

**Backend routes:** `/api/…` and `/api/v1/…` are equivalent (`config/urls.py`).

---

## 1. Entry and authentication

```mermaid
flowchart TD
  A[App launch] --> B{Hydrate session}
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

  Today --> DV[Daily verse card]
  DV --> Verse["/verse/ch.vrs"]
  Verse --> Note[Verse note API]
  Verse --> RO[reading/verse-open]

  Today --> AskTab[Go to Ask]
  Today --> ReadTab[Go to Read library]
  Today --> ProfileBtn[Profile / settings entry]

  Today --> NH[Naam japa section]
  Today --> CH[Community preview]
  CH --> CommFull["/community"]

  ProfileBtn --> Profile["/profile"]
  Profile --> Saved[saved-reflections list]
  Profile --> Acct["/account"]
  Profile --> Notif["/notifications"]
  Profile --> Plans["/plans"]
  Profile --> Support["/support"]
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

```mermaid
flowchart TD
  Entry[From Today / Meditate CTAs]

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

## 14. Typical journey (qualitative)

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
- **Account:** **Profile** (stack) → **Plans**, **notifications**, **account**, **support**.

---

*Last aligned with Expo tab layout and routes: 2026-04-27.*
