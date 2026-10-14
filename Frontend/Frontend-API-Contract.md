# Frontend → Backend API Contract

The JSON (and file-blob) responses the frontend expects from the backend, derived from the
Vue views in `Frontend/src/views/`. Every view that calls the API is covered below.

---

## Global Conventions

### Base URL

`Frontend/src/api/client.js`:

```js
baseURL: import.meta.env.VITE_API_BASE_URL || '/api'
```

Every relative path in this document resolves against that base. `GET /auth/login` therefore
becomes `GET /api/auth/login` by default.

### Authentication

- Every request is sent with `Authorization: Bearer <token>`, populated automatically from
  `stores/auth`.
- The token is the one returned by `/auth/login` or `/auth/register`.

### Response shape

Data fields are returned at the **top level** of the response body. Views read
`response.data.<field>` or `response.data.<collection>` directly; responses are not wrapped.

### Error shape

Error responses are sent as:

```json
{ "message": "Human-readable error string" }
```

The client interceptor reads `error.response.data.message` and displays it as a toast; if it
is absent, a generic `"Server Error (<status>)"` message is shown instead. A `401` also
clears the auth session and redirects to the login page.

### File responses

Endpoints documented as **blob** return raw binary or text (`responseType: 'blob'`), not JSON.
PDF endpoints are consumed as `application/pdf`; the admin log/export endpoints are consumed
as `.txt` and `.csv` respectively.

---

## 1. Auth — `LoginRegisterView.vue`

### 1.1 `POST /auth/login`

Request:

```json
{ "hash": "string", "password": "string" }
```

Response `200`:

```json
{
  "user": {
    "name": "string",
    "role": "delegate | advisor | chair | admin"
  },
  "token": "string"
}
```

Field notes:
- `user.name` is used in the welcome toast (falls back to `"User"`).
- `user.role` determines the post-login redirect: `/{role}/dashboard`.

### 1.2 `POST /auth/register`

Request: identical to login (`{ hash, password }`).

Response `200`: identical to login (`{ user, token }`).

---

## 2. Delegate — `DelegateDashboardView.vue`

### 2.1 `GET /delegate/my-assignment`

```json
{
  "announcements": ["string"],
  "delegate": {
    "committee": "string",
    "country": "string"
  },
  "conferenceLinks": [
    { "text": "string", "url": "string" }
  ],
  "positionPaper": {
    "status": "unsubmitted | submitted | graded",
    "score": "string | number",
    "feedback": "string",
    "instructions": ["string"],
    "criteria": [
      { "id": "string | number", "label": "string", "score": 8, "maxScore": 10 }
    ]
  }
}
```

Field notes:
- `announcements` is rendered as one line each in the bar at the top of the page, in the
  order sent, and the bar is hidden when the list is empty. The backend caps this at 3
  (2 general + 1 for the delegate's own committee), sending general lines first, so the
  bar can never overflow.
- `conferenceLinks` is padded/trimmed client-side to exactly 5 slots; surplus entries are
  ignored. The backend caps the total at 5 (2 general + 3 for the delegate's committee),
  so nothing is normally dropped.
- `instructions` renders as an ordered list.
- `delegate.committee` and `delegate.country` fall back to `"Unassigned"` when empty.
- `score`, `feedback`, and `criteria` populate the **Grade & Chair Feedback** panel and are
  only displayed when `positionPaper.status` is `"graded"`. While the paper is `"submitted"`
  or `"unsubmitted"` the panel shows a waiting message instead.
- `criteria` supplies the per-criterion breakdown: each row renders `label`, `score`,
  `maxScore`, and a bar showing `score / maxScore`. Leave it empty until the paper is graded.
  The backend must join the chair's stored `scores` map (see §6.3) against the grading rubric
  (see §6.1) to resolve `label` and `maxScore` — a delegate cannot read `/chair/rubric`.
- `feedback` is the chair's written comment (see §6.3); when graded without a comment it
  falls back to "No comments were provided."
- `score` is rendered verbatim as the final score, so send it pre-formatted (e.g. `"18/20"`).

### 2.2 `POST /delegate/upload-paper`

Request: `multipart/form-data` with a single field named **`paper`** (PDF).

Response: body is not read; only the status code matters.

---

## 3. Advisor — `AdvisorDelegatesView.vue`

### 3.1 `GET /advisor/delegates`

```json
{
  "delegates": [
    {
      "id": 1,
      "country": "string",
      "committee": "string",
      "paperStatus": "unsubmitted | submitted | graded",
      "paperGrade": "string | null",
      "hash": "string",
      "registered": true
    }
  ],
  "total": 12
}
```

Field notes:
- `total` is shown in the stats bar; `delegates` drives the list.
- `hash` is masked as `••••••••` until hashes are revealed via §3.3.
- `paperStatus` must be one of the three literals: it selects the badge style and disables the
  download button when `"unsubmitted"`.
- `paperGrade` displays as `"N/A"` when falsy.

### 3.2 `GET /advisor/delegates/{delegateId}/paper`

Response: **blob** — PDF, saved as `delegate_<id>_paper.pdf`.

### 3.3 `POST /advisor/verify-hashes`

Request:

```json
{ "password": "string" }
```

Response `200`:

```json
{ "delegates": [ /* delegate objects as in §3.1, with real `hash` values */ ] }
```

Field notes:
- On failure, the 4xx body's `message` is shown inside the password modal, falling back to
  `"Incorrect password. Access denied."`.

---

## 4. Advisor — `AdvisorSchoolView.vue`

### 4.1 `GET /advisor/school`

```json
{
  "school": {
    "name": "string",
    "address": "string",
    "city": "string",
    "state": "string",
    "zip": "string",
    "advisorName": "string",
    "advisorEmail": "string",
    "advisorPhone": "string",
    "headDelegateName": "string",
    "headDelegateEmail": "string",
    "headDelegatePhone": "string"
  },
  "billing": {
    "invoiceUrl": "string",
    "paymentStatus": "paid | partially paid | unpaid"
  },
  "checklist": [
    { "label": "string", "completed": true }
  ]
}
```

Field notes:
- Empty string values render as `"N/A"` in the school panels.
- `billing.paymentStatus` is matched case-insensitively; `paid`, `partially paid`, and `unpaid`
  (default) each have a distinct badge style.
- `billing.invoiceUrl` renders as a link when present, otherwise "No invoice available".
- `checklist[].completed` toggles the check indicator on each row.
- `checklist` labels are conference-wide, but `completed` is **this school's own tick**
  (`checklist_progress`, §8.7) — another school ticking a line does not affect this one.
  Before an admin fills the labels in it returns `[]`, which renders the panel empty.

---

## 5. Chair — `ChairCommitteeView.vue`

### 5.1 `GET /chair/committee/overview`

```json
{
  "chairName": "string",
  "committeeName": "string",
  "delegatesRegistered": 10,
  "totalDelegates": 15,
  "papersGraded": 4,
  "totalPapersSubmitted": 7,
  "timeline": {
    "preConference": [
      { "label": "string", "timestamp": "ISO-8601 date string" }
    ],
    "duringConference": [
      { "label": "string", "timestamp": "ISO-8601 date string" }
    ]
  }
}
```

Field notes:
- `timeline` must always contain both keys, even when empty; the template iterates both directly.
- `timestamp` must be a parseable date string. It is compared against the current time to derive
  each event's completed/active/upcoming status, and is formatted for display.
- Each `timestamp` carries an explicit UTC offset (`2026-10-10T16:00:00+00:00`). The database
  stores naive UTC, but `new Date("2026-10-10T16:00:00")` in a browser would read that as *local*
  time and shift every event by the viewer's offset — so the offset is part of the contract, not
  decoration. Both lists arrive sorted by time ascending, because the view uses the next event's
  time as the end of the current window.
- Counts render as `delegatesRegistered / totalDelegates` and `papersGraded / totalPapersSubmitted`.

---

## 6. Chair — `ChairGradingView.vue`

### 6.1 `GET /chair/rubric`

```json
[
  { "id": "string | number", "label": "string", "maxScore": 10 }
]
```

Field notes:
- `id` is the list key and the key used in the `scores` map.
- `maxScore` values are summed to compute the maximum possible total.
- This is the grading rubric. The awards rubric at `/chair/awards/rubric` (§7.2) has a
  different shape.

### 6.2 `GET /chair/delegates`

```json
[
  {
    "id": 1,
    "country": "string",
    "committee": "string",
    "status": "unsubmitted | submitted | graded",
    "submissionDate": "string",
    "totalScore": "string",
    "scores": { "<rubricId>": 8 },
    "comments": "string",
    "pdfUrl": "string"
  }
]
```

Field notes:
- Top-level array.
- `status` gates the View & Grade and PDF buttons (`"unsubmitted"` disables both).
- `scores` keys correspond to rubric `id` values.
- `submissionDate` and `totalScore` are display strings.
- `pdfUrl` is bound directly to an `<iframe>` src, so it must be a URL loadable without the
  Authorization header (e.g. a signed URL).

### 6.3 `POST /chair/papers/{delegateId}/grade`

Request:

```json
{
  "delegateId": 1,
  "scores": { "<rubricId>": 8 },
  "totalScore": "18/20",
  "comments": "string"
}
```

Field notes:
- `totalScore` is a **string** in `"<earned>/<max>"` form.

Response: body is not read.

### 6.4 `GET /chair/papers/{delegateId}/download`

Response: **blob** — PDF, saved as `<country>_Position_Paper.pdf`.

---

## 7. Chair — `ChairAwardsView.vue`

### 7.1 `GET /chair/awards/options`

```json
["Verbal Commendation", "Honorable Mention", "Outstanding Delegate", "Best Delegate"]
```

Field notes:
- Top-level array of strings.
- `"None"` and `"Candidate"` are built into the template and must not be included here.

### 7.2 `GET /chair/awards/rubric`

```json
[
  {
    "id": "string | number",
    "label": "string",
    "levels": [
      { "score": 4, "label": "string", "description": "string" }
    ]
  }
]
```

Field notes:
- `levels[].score` is both the list key and the value stored in `scores`.
- Each criterion's maximum is derived client-side as the highest `level.score`.
- One score per criterion is stored, selected by clicking a level cell.

### 7.3 `GET /chair/awards/delegates`

```json
[
  {
    "id": 1,
    "country": "string",
    "committee": "string",
    "assignedAward": "Candidate | Verbal Commendation | Honorable Mention | Outstanding Delegate | Best Delegate | None",
    "scores": { "<criterionId>": 4 },
    "totalScore": 12
  }
]
```

Field notes:
- `assignedAward` drives both the summary counters and the card colour class; it must match one
  of the listed values.
- `totalScore` renders as `"<n> pts"` and is hidden when `null`.

### 7.4 `POST /chair/awards/{delegateId}`

Request:

```json
{
  "delegateId": 1,
  "assignedAward": "Honorable Mention",
  "scores": { "<criterionId>": 4 },
  "totalScore": 12
}
```

Field notes:
- `totalScore` is a **number** here.
- The frontend requires every rubric criterion to be scored before an official award
  (anything other than `"None"` or `"Candidate"`) can be assigned.

Response: body is not read.

---

## 8. Admin — `AdminDashboardView.vue`

### 8.1 `GET /admin/dashboard-stats`

```json
{
  "totalDelegates": 128,
  "committeeCounts": [
    { "committee": "DISEC", "count": 42 }
  ],
  "storage": {
    "usedGb": 12.4,
    "totalGb": 100
  },
  "downtimeEvents": [
    {
      "id": 1,
      "startTime": "string",
      "endTime": "string",
      "duration": "string",
      "reason": "string"
    }
  ]
}
```

Field notes:
- `committeeCounts[].committee` is the list key and the displayed committee name.
- `storage.totalGb` of `0` renders the capacity bar at `0%`.
- `startTime`, `endTime`, and `duration` are pre-formatted display strings.
- An empty `downtimeEvents` array renders the "100% Uptime" message.

### 8.2 `GET /admin/ports/health`

```json
[
  { "name": "Backend API", "port": 8000, "status": "healthy" },
  { "name": "Database", "port": 5432, "status": "unreachable" }
]
```

Field notes:
- Top-level array; `port` is the list key and must be unique.
- `status` must be exactly `"healthy"` or `"unreachable"`; any other value renders as unreachable.

### 8.3 File downloads

| Endpoint | Response |
| --- | --- |
| `GET /admin/logs/business.txt` | **blob** — plain text |
| `GET /admin/logs/technology.txt` | **blob** — plain text |
| `GET /admin/export/database.csv` | **blob** — CSV |

Field notes:
- Fetched with `responseType: 'blob'` and saved as `business-log.txt`, `technology-log.txt`,
  and `database-export.csv` respectively.

### 8.4 Delegate hashes

Moved here from the retired CLI app (`administrator.py`). They now live under the
admin router, so they require an admin session like the rest of §8.

#### 8.4.1 `POST /admin/hashes`

Request:

```json
{
  "school_name": "Lincoln High School",
  "finalAssignments": {
    "1": ["DISEC", "General Assembly", "France"]
  }
}
```

Field notes:
- `school_name` identifies the school the new delegates belong to. It must match an
  existing school; an unknown name returns `404` with a `{"message": ...}` body.
- `finalAssignments` keys are the per-school labels the form uses as row positions
  ("1", "2", …); the backend turns each into the `<school> - #<key>` display name.
  Its value is positional — `[committee, committeeType, country]` (the CLI's
  `FinalAssignments` shape). `committeeType` is accepted but not persisted: there is no
  column for it.
- A `(committee, country)` pair that already has an account is rejected with `409`
  ("regenerate" is the intended way to reissue). Double-delegation partners share one
  account, so they are submitted once and share one hash.

Response `201`:

```json
{
  "hashes": [
    { "name": "Lincoln High School - #1", "hash": "hash123abc" }
  ]
}
```

Field notes:
- One entry per submitted delegate, in submission order. `name` is the label the backend
  built, and `hash` is the freshly minted login hash — the only time it is sent in
  clear text apart from `GET /admin/hashes`.

#### 8.4.2 `POST /admin/hashes/regenerate/delegate`

Request:

```json
{ "committee": "DISEC", "country": "France" }
```

Response `200`:

```json
{ "name": "France (DISEC)", "hash": "hash789ghi" }
```

#### 8.4.3 `POST /admin/hashes/regenerate/school`

Request:

```json
{ "school": "Lincoln High School" }
```

Response `200`: `{ "hashes": [ { "name": "string", "hash": "string" } ] }`

#### 8.4.4 `DELETE /admin/hashes`

Request:

```json
{ "countryAndCommitteeList": [["France", "DISEC", "General Assembly"]] }
```

Field notes:
- Each entry is `[country, committee, committeeType]` (the CLI's `CountryAndCommitteeList`).

Response `200`:

```json
{ "dropped": [ { "name": "string", "hash": "string" } ] }
```

#### 8.4.5 `GET /admin/hashes`

Query: `schoolName` (optional) — narrows the list to a single school.

Response `200`: `{ "hashes": [ { "name": "string", "hash": "string" } ] }`

### 8.5 `GET /admin/awards`

```json
{
  "committees": [
    {
      "committee": "DISEC",
      "awards": [
        { "country": "France", "award": "Best Delegate" }
      ]
    }
  ]
}
```

Field notes:
- Read-only, conference-wide report of assigned awards. The writable, chair-scoped award
  routes remain §7.4.
- `committees[].committee` is the list key; `awards[].country` is the per-row key.

### 8.6 Announcements & conference links

The lines delegates see on their dashboard (§2.1). An admin edits them from the
**Delegate Content** tab. `kind` selects the strip: `announcement` feeds the bar at
the top of the delegate page, `link` feeds the five slots in the "Conference & General
Info" panel.

`committee_name` is `null` for a line addressed to every delegate, or a committee name to
reach only that committee. Timestamps are **naive UTC** (no timezone suffix); the admin UI
converts to and from the browser's local time. `starts_at` null means live immediately,
`ends_at` null means no planned end.

**Capacity** is enforced per target, counting lines that have not ended yet — an expired
line releases its place, a scheduled one already holds it, so the totals below are a hard
ceiling on what any delegate sees at once:

| kind | global (`committee_name: null`) | per committee | most a delegate can see |
| --- | --- | --- | --- |
| `announcement` | 2 | 1 | 3 |
| `link` | 2 | 3 | 5 |

Overflowing a target returns `409`; fix it by deleting a line or editing another one to end
sooner. There is no soft-delete flag — `DELETE` is permanent.

#### 8.6.1 `GET /admin/broadcasts`

Query: `kind` (optional, `announcement` | `link`).

Response `200`:

```json
{
  "broadcasts": [
    {
      "id": 1,
      "kind": "announcement",
      "body": "Buses depart at 7:30am",
      "url": null,
      "committee_name": null,
      "position": 0,
      "starts_at": null,
      "ends_at": "2026-10-05T18:00:00",
      "created_at": "2026-10-03T21:16:00",
      "updated_at": null
    }
  ]
}
```

Field notes:
- Editor view: ended rows are included, so they can still be edited or deleted.

#### 8.6.2 `GET /admin/committees`

Response `200`: `["DISEC", "WHO"]` — committee names, for the target picker.

#### 8.6.3 `POST /admin/broadcasts`

Request:

```json
{
  "kind": "link",
  "body": "Conference schedule",
  "url": "https://example.com/schedule",
  "committee_name": "DISEC",
  "position": 0,
  "starts_at": null,
  "ends_at": null
}
```

Response `201`: one broadcast entry, as in §8.6.1.

Field notes:
- `body` is the announcement text, or the link's label; it may not be blank.
- `url` is required for a `link` and rejected on an `announcement`.
- `committee_name` must be an existing committee (`404` otherwise).
- `ends_at` must be after `starts_at` when both are given (`400`).
- A create that would exceed the target's capacity returns `409`.

#### 8.6.4 `PATCH /admin/broadcasts/{id}`

Request: any subset of `body`, `url`, `committee_name`, `position`, `starts_at`, `ends_at`.
Only the keys present are applied, so `"ends_at": null` clears the end date while omitting
it leaves it alone. `kind` is fixed at creation.

Response `200`: the updated broadcast entry. The capacity is re-checked against the new
target and schedule, so moving a line to a busier committee can return `409`; `404` if the
id does not exist.

#### 8.6.5 `DELETE /admin/broadcasts/{id}`

Response `204` with no body. Permanent; `404` if the id does not exist.

### 8.7 Conference checklist

The **Conference Action Checklist** panel on the advisor dashboard (§4.1) is split across two
tables, and the split is the whole point:

| table | holds | scope |
| --- | --- | --- |
| `conference_checklist` | `id`, `label`, `position` | every school shares these lines |
| `checklist_progress` | `school_id`, `item_id`, `completed` | one row per school that has ticked a line; a pair with no row means "not done" |

So the labels are edited once, while each school's ticks are its own — Lincoln paying its
invoice does not tick Rival's box. Both are edited from the **Delegate Content** tab.

Because `checklist_progress.item_id` points at `conference_checklist.id`, the admin route
**reconciles lines by id**: a line sent with an id is updated in place (so its schools' ticks
survive a rename), a line with no id is created, and a line that is absent from the request
is deleted along with every school's progress for it. Labels must be unique,
case-insensitively, so a line can also be addressed by name.

Limits: at most **20** lines, each label 200 characters or fewer after trimming, no blank
labels and no duplicates (`400` otherwise).

#### 8.7.1 `GET /admin/schools`

Response `200`: `{ "schools": [ { "id": 7, "name": "Lincoln High School" } ] }` — `id` is
`schools.account_id`. Used by the progress picker, and by a script that needs the ids.

#### 8.7.2 `GET /admin/checklist`

The shared lines, in display order.

```json
{ "items": [ { "id": 3, "label": "Submit position papers" } ] }
```

#### 8.7.3 `PUT /admin/checklist`

Request — the whole set of lines, in the order they should appear:

```json
{
  "items": [
    { "id": 3, "label": "Submit every position paper" },
    { "label": "Book the bus" }
  ]
}
```

Field notes:
- `id` omitted creates a new line; `id` present renames/reorders the existing one and keeps
  its ticks. Line `1` above is deleted, and with it every school's tick for it.
- Response `200`: the saved lines, as in §8.7.2; `{"items": []}` clears the checklist for
  everyone. `400` for a blank, over-long or duplicate label, a repeated id, or more than 20
  lines; `404` for an unknown id.

#### 8.7.4 `GET /admin/schools/{id}/checklist`

One school's checklist: every shared line, plus that school's tick.

```json
{
  "school_id": 7,
  "school_name": "Lincoln High School",
  "items": [ { "id": 3, "label": "Submit position papers", "completed": true } ]
}
```

Field notes:
- `school_name` is echoed so a script can confirm it addressed the school it meant to.
- `404` if the school does not exist.

#### 8.7.5 `PATCH /admin/schools/{id}/checklist`

Tick or untick lines for one school.

```json
{
  "items": [
    { "id": 3, "completed": true },
    { "label": "Pay the conference fee", "completed": false }
  ]
}
```

Field notes:
- **Partial**: lines not listed keep their current state, so a script can set one line
  without knowing the rest. The admin UI sends every line, which amounts to a full save.
- Each entry gives **exactly one** of `id` or `label` (the label is matched
  case-insensitively after trimming); `completed` is required. `400` if both or neither is
  given, `404` for an unknown line or school.
- Response `200`: the school's checklist afterwards, as in §8.7.4.
- Idempotent, so it is safe to replay. A script driving it:

```python
import requests

BASE = "https://your-host/api"
headers = {"Authorization": f"Bearer {token}"}

# tick a line by name, leaving every other line as it is
requests.patch(
    f"{BASE}/admin/schools/7/checklist",
    headers=headers,
    json={"items": [{"label": "Pay the conference fee", "completed": True}]},
    timeout=10,
).raise_for_status()
```

### 8.8 Conference timeline

The schedule shown on every chair's committee overview (§5.1) is a single conference-wide list
in `timeline_events`, edited from the admin **Timeline** tab. It is universal — every committee
runs on the same schedule — and purely time-based: there is no completion flag and no per-chair
tick, because the chair dashboard derives each event's completed / in progress / upcoming state
by comparing its time with the clock.

That is why ordering matters and why the payload carries no order: events come back sorted by
`starts_at` ascending, and the view treats each event's time as the start of a window that ends
at the next event (the last pre-conference event bridges into the first during-conference one).

Limits: at most **30** events, each label 200 characters or fewer after trimming, no blank
labels, and `starts_at` must be **naive UTC** — an aware value with a timezone suffix is
rejected (`400`) rather than silently shifted by the database session's offset.

#### 8.8.1 `GET /admin/timeline`

```json
{
  "events": [
    { "id": 3, "phase": "preConference", "label": "Opening Ceremony", "starts_at": "2026-10-09T18:00:00" }
  ]
}
```

Field notes:
- `starts_at` is naive UTC here, matching every other admin payload, so it round-trips through
  `PUT` unchanged. §5.1 is where it gains the explicit offset the browser needs.

#### 8.8.2 `PUT /admin/timeline`

Request — the whole schedule; nothing references an event, so it is replaced outright:

```json
{
  "events": [
    { "phase": "preConference", "label": "Registration", "starts_at": "2026-10-09T15:00:00" },
    { "phase": "duringConference", "label": "Committee Session 1", "starts_at": "2026-10-10T09:00:00" }
  ]
}
```

Field notes:
- `phase` is `preConference` or `duringConference`; `id` is not accepted (events have no
  identity to preserve).
- Submission order is irrelevant — the response is sorted by time.
- Response `200`: the saved events, as in §8.8.1. `{"events": []}` clears the schedule, which
  every chair then sees as two empty lists.

---

## Quick Reference

| # | View | Method | Path (relative to `/api`) | Response |
| --- | --- | --- | --- | --- |
| 1 | Auth | POST | `/auth/login` | `{user, token}` |
| 2 | Auth | POST | `/auth/register` | `{user, token}` |
| 3 | Delegate | GET | `/delegate/my-assignment` | dashboard object |
| 4 | Delegate | POST | `/delegate/upload-paper` | (ignored) |
| 5 | Advisor | GET | `/advisor/delegates` | `{delegates[], total}` |
| 6 | Advisor | GET | `/advisor/delegates/{id}/paper` | blob PDF |
| 7 | Advisor | POST | `/advisor/verify-hashes` | `{delegates[]}` |
| 8 | Advisor | GET | `/advisor/school` | `{school, billing, checklist}` |
| 9 | Chair | GET | `/chair/committee/overview` | overview object |
| 10 | Chair | GET | `/chair/rubric` | `[{id, label, maxScore}]` |
| 11 | Chair | GET | `/chair/delegates` | delegate array |
| 12 | Chair | POST | `/chair/papers/{id}/grade` | (ignored) |
| 13 | Chair | GET | `/chair/papers/{id}/download` | blob PDF |
| 14 | Chair | GET | `/chair/awards/options` | `[string]` |
| 15 | Chair | GET | `/chair/awards/rubric` | `[{id, label, levels[]}]` |
| 16 | Chair | GET | `/chair/awards/delegates` | delegate array |
| 17 | Chair | POST | `/chair/awards/{id}` | (ignored) |
| 18 | Admin | GET | `/admin/dashboard-stats` | stats object |
| 19 | Admin | GET | `/admin/ports/health` | port array |
| 20 | Admin | GET | `/admin/logs/business.txt` | blob text |
| 21 | Admin | GET | `/admin/logs/technology.txt` | blob text |
| 22 | Admin | GET | `/admin/export/database.csv` | blob CSV |
| 23 | Admin | POST | `/admin/hashes` | `{hashes[]}` |
| 24 | Admin | POST | `/admin/hashes/regenerate/delegate` | `{name, hash}` |
| 25 | Admin | POST | `/admin/hashes/regenerate/school` | `{hashes[]}` |
| 26 | Admin | DELETE | `/admin/hashes` | `{dropped[]}` |
| 27 | Admin | GET | `/admin/hashes?schoolName=` | `{hashes[]}` |
| 28 | Admin | GET | `/admin/awards` | `{committees[]}` |
| 29 | Admin | GET | `/admin/broadcasts?kind=` | `{broadcasts[]}` |
| 30 | Admin | POST | `/admin/broadcasts` | broadcast entry |
| 31 | Admin | PATCH | `/admin/broadcasts/{id}` | broadcast entry |
| 32 | Admin | DELETE | `/admin/broadcasts/{id}` | (204, no body) |
| 33 | Admin | GET | `/admin/committees` | `[string]` |
| 34 | Admin | GET | `/admin/schools` | `{schools[]}` |
| 35 | Admin | GET | `/admin/checklist` | `{items[]}` |
| 36 | Admin | PUT | `/admin/checklist` | `{items[]}` |
| 37 | Admin | GET | `/admin/schools/{id}/checklist` | `{school_id, school_name, items[]}` |
| 38 | Admin | PATCH | `/admin/schools/{id}/checklist` | same as `GET` |
| 39 | Admin | GET | `/admin/timeline` | `{events[]}` |
| 40 | Admin | PUT | `/admin/timeline` | `{events[]}` |

**Roles** (from the router): `delegate`, `advisor`, `chair`, `admin`. Chair views also accept
`admin`.
