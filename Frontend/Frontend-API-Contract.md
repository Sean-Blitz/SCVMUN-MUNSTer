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

### Field validation (`422`)

Request bodies are validated against the same length limits as the database columns, so an
over-long value is rejected before it reaches Postgres (which would answer with a `500`). The
body is the usual `{"message": ...}`, written as a sentence because it goes straight into the
toast:

```json
{ "message": "Advisor phone must be at most 20 characters." }
```

- Up to three problems are reported at once, joined by `; `:
  `"School address must be at most 200 characters; zip code must be at most 10 characters."`
- A missing field reads `"Advisor name is required."`; a nested entry names its row:
  `"FinalAssignments (entry 1) must be at most 100 characters."`
- Limits come from `crud/database_schema.py` — see `schemas/request_models.py` for the
  mapping. Storage limits live in the models; business rules that need their own wording
  (blank or duplicate checklist labels, an unsupported `payment_status`, a delegate triple
  that is not three items) stay in the endpoints and still return `400`.

### File responses

Endpoints documented as **blob** return raw binary or text (`responseType: 'blob'`), not JSON.
PDF endpoints are consumed as `application/pdf`; the admin log/export endpoints are consumed
as `.txt` and `.csv` respectively.

---

## 1. Auth — `LoginRegisterView.vue`

Both routes are **pre-auth** and can require a Cloudflare Turnstile token, sent in the
`X-Turnstile-Token` header (not the JSON body, so the body contract stays as below).

- Required only when the server has `TURNSTILE_SECRET` set. Without it the header is ignored,
  which is how development and the test suite run; the API writes `captcha.disabled` to the
  technical log at startup so a production deploy cannot miss it.
- Three things are checked server-side, not just `success`: the **action** must be `auth`
  (the widget's configured action), the token must not be older than 5 minutes or reused, and
  the **hostname** Siteverify reports must be in the server's `TURNSTILE_HOSTNAMES` allow-list.
  An empty allow-list rejects everything rather than accepting any hostname.
- A missing, expired (>5 min), reused or forged token → `400` with
  `{"message": "Please complete the human check and try again."}`. The view shows that in a
  toast and resets the widget, because Turnstile tokens are single-use.
- Cloudflare unreachable → `503` `"The human check is unavailable right now. Please try again
  in a moment."` Fail-closed, but the visitor is told it is not their fault.
- The site key is `VITE_TURNSTILE_SITE_KEY`, baked in at build time: a production build must
  be made with it set, or the widget is compiled out while the server still demands a token.
  The two keys are a pair — set both or neither.

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

### 1.3 `POST /auth/logout`

Revokes the session behind the `Authorization: Bearer` token. No body.

Response `204`, always — including with no token, an unknown token, or a token that has
already been logged out. Logout is idempotent by design: the client has signed the user out
locally either way, and a `401` here would only put an error toast on top of a successful
sign-out.

- Removes **only the presented session**, so a second device stays signed in. Reissuing a
  hash still revokes every session for that account.
- The view calls it best-effort before clearing local state; a network failure does not
  stop the sign-out.
- `authStore` persists `token`/`user` in `localStorage` on login and clears them on logout,
  so a refresh keeps the session and signing out leaves nothing behind.

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

Field notes:
- Re-uploading is allowed until a chair has graded the paper (`409` after that); each upload is
  its own row, and the newest one is what everything downstream serves.
- **Storage is bounded to one file per delegate.** The previous file is deleted once the new
  one is committed — the rows stay as history, but only the live paper's bytes exist. The
  sweep runs after the commit and keeps *the newest row's* file, so two overlapping uploads
  cannot leave two files behind: whichever request finishes last removes the other's.
- **At most `MAX_UPLOADS_PER_HOUR` (5) uploads per delegate in a rolling hour**, then `429` with
  a `Retry-After` header. That is per *account*, independent of nginx's per-IP limits.
- Rejections: `400` if the file is not a PDF (checked by the `%PDF-` signature, not just the
  name), `413` if it exceeds `PAPER_MAX_MB`, `404` if the account has no delegate profile,
  `429` for the hourly cap. nginx also answers `429` with the same `{"message": ...}` shape
  when the per-IP rate is exceeded before the request reaches the app.
- Dropping a delegate through the admin hash tooling deletes its stored paper as well.

### 2.3 `GET /delegate/my-paper`

Response: **blob** — the caller's own position paper as a PDF, saved by the view as
`<country>_Position_Paper.pdf`.

Field notes:
- Scoped by the token: there is no delegate id in the path, so a delegate can only ever fetch
  their own paper.
- The newest upload is served, matching the `positionPaper.status` reported by §2.1.
- `404` with a message distinguishing "nothing submitted yet" from "the stored file is missing".
  The view only shows the button once something has been submitted, but a file deleted from the
  storage volume behind the API's back still lands here.

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
    "submissionDate": "2026-10-04T19:00:00+00:00",
    "totalScore": "string",
    "scores": { "<rubricId>": 8 },
    "comments": "string"
  }
]
```

Field notes:
- Top-level array; scoped to the chair's own committee, ordered by country.
- `status` gates the View & Grade and PDF buttons (`"unsubmitted"` disables both).
- `scores` keys correspond to rubric `id` values; a stored mark that is not a number is dropped.
- `totalScore` is a display string (e.g. `"18/20"`), empty until the paper is graded.
- `submissionDate` is the newest upload's time as an ISO-8601 instant **with a UTC offset**, so
  the view can localise it — the column is naive UTC, and `new Date("…")` without an offset would
  read it as the viewer's local time. Empty for a delegate who has never uploaded.
- **There is no `pdfUrl`.** An `<iframe src>` does not send the Authorization header, so the view
  fetches §6.4 as a blob through the API client and previews the resulting object URL. Signing a
  URL instead would have made each paper reachable by a link that outlives the session.

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
- `totalScore` is a **string** in `"<earned>/<max>"` form, but the server **recomputes** it as
  `<sum of scores>/<sum of rubric maxima>` and stores that; the submitted value is ignored, so a
  client cannot record a score line that disagrees with the rubric. The denominator is always the
  whole rubric, so an unscored criterion counts as zero rather than shrinking the maximum.
- `delegateId` in the body is ignored — the path segment is authoritative.
- `scores` keys must be criteria from §6.1, and each mark must be between `0` and that
  criterion's `maxScore` (`400` otherwise; the input's `max` attribute is only a hint).
- `comments` are capped at 500 characters; a blank comment stores `null`, so §2.1's
  "No comments were provided." fallback applies.
- Grading sets `paper_status` to `"graded"`, which is what then makes §2.2 refuse a replacement
  upload. Re-grading is allowed and overwrites the previous marks — a chair correcting a mistake.
- Grading a delegate who has not submitted returns `409`; a delegate outside the chair's committee,
  or a chair profile that does not exist, returns `404`. `400` also if the grading rubric has no
  criteria configured, because grading against nothing would store a meaningless `"0/0"`.

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
- `totalScore` renders as `"<n> pts"` and is hidden when `null`. It is `null` until a chair has
  saved something for that delegate, and it is the sum of `scores` — stored as a float, so a
  fractional level score (2.5) is not rounded.
- `scores` is the stored `{criterionId: mark}` map; a stored entry that is not a number is
  dropped rather than failing the roster.

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
- `totalScore` is a **number** here, but the server **recomputes** it as the sum of `scores` and
  stores that — the total is derived, and a client that disagreed would put a wrong number in
  front of the chair. `delegateId` in the body is likewise ignored; the path segment wins.
- The frontend requires every rubric criterion to be scored before an official award
  (anything other than `"None"` or `"Candidate"`) can be assigned, and the API enforces the same
  rule: an incomplete set returns `400` naming the missing criteria, so a script cannot store an
  award that was never evaluated.
- `scores` keys must be criteria from §7.2 — an unknown id returns `400` rather than being
  parked in the database.
- `assignedAward` must be one of §7.1's names plus `"None"` and `"Candidate"`; anything else
  returns `400`.
- Deleting a delegate from the chair's committee scope answers `404`. Saving `"None"` with no
  marks clears the stored scores and resets `totalScore` to `null`.

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
- `storage` is the filesystem the API runs on (`STORAGE_PATH`, default `/`), as used/total
  GiB rounded to one decimal — the same numbers `df -h` shows, so they can be compared with a
  terminal. An unreadable path reports `0`/`0`, which renders the bar at `0%`, rather than
  failing the whole dashboard.
- `startTime`, `endTime`, and `duration` are pre-formatted display strings: `"Oct 13, 05:59 UTC"`
  and `"12m 30s"` / `"1h 1m"` / `"2d 7h"`. UTC is stated explicitly because the server does not
  know the browser's timezone and these are read by whoever is on call.
- An empty `downtimeEvents` array renders the "100% Uptime" message. That is also what a fresh
  install shows before the monitor has any data.

**Where downtime comes from.** There is no uptime service to ask, so the API keeps its own
evidence (see `core/monitor.py`): a heartbeat every 30 s, and an outage inferred when the next
heartbeat arrives more than 60 s after the last one. Two files under `LOG_DIR`:

| file | written | read by |
| --- | --- | --- |
| `heartbeat.log` | a timestamp every beat, trimmed to the last 5 lines | gap detection only |
| `downtime.log` | one line per detected outage, appended, never trimmed | this endpoint's 7-day report |

Design points worth knowing when reading the dashboard:
- The threshold is **two intervals**, so a normal `systemctl restart` or one starved thread is
  not recorded as downtime; anything a human would notice is.
- The reason distinguishes the two cases: `"service restart"` when the gap was found by the
  first beat after startup (the process was not running — crash, reboot, deploy), `"heartbeat
  gap"` when it was found mid-run (the process was up but the thread stalled).
- An outage is **inferred**: nothing can report an outage while it is down, so `endTime` is when
  the API came back, not necessarily when the machine did.
- A gap over 30 days is treated as a clock jump (NTP step, restored snapshot) and ignored rather
  than recorded as a month-long outage.
- History is kept in `downtime.log` rather than derived from `heartbeat.log`, because the
  heartbeat file only holds a couple of minutes of beats.

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
- Both logs are plain text, one event per line, appended to. They are **never** an error body: a
  log that has not been written yet downloads as an empty file, because the view saves whatever
  bytes come back and a JSON error would end up inside the downloaded `.txt`.
- A line reads `2026-10-14T05:26:52Z login.failed actor=chair:2 hash=CHAI…(6) reason=bad_password`
  — a UTC timestamp, an `action`, then `key=value` fields (values containing spaces are quoted).

**Which log gets what** (a convention, since nothing in the code can enforce it):

| `technology.txt` | `business.txt` |
| --- | --- |
| logins and their failures, registrations, hash issuing/reissuing/dropping, hash reveals, database setup | papers submitted and graded, awards assigned, announcements published/edited/withdrawn, checklist labels and per-school progress, timeline changes |

Conventions worth knowing:
- **No access code is ever written in full.** Login lines record a masked fragment
  (`AB12…(16)`) — enough to correlate a code with an account, not enough to use it. The
  technical log is still sensitive and is written mode `0600`.
- `actor` is `role:id`, so it survives a rename; `-` means no caller (a script).
- One action can legitimately appear in both logs when it is both a credential and a business
  event: dropping delegates revokes their codes (technical) *and* changes the roster (business).
- Location is `LOG_DIR`, defaulting to `Backend/logs`; on the server point it somewhere durable
  such as `/var/log/scvmun`, owned by the account that runs the API.

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
- `school_name` identifies the school the new delegates belong to. **This endpoint does not
  create the school** (it was named `create_school_or_delegate_hashes` before the split, and
  no school was ever created there): an unknown name returns `404` pointing at
  `POST /admin/schools`, which creates the school, its advisor account and the advisor's
  hash. Create first, then mint delegates.
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

#### 8.7.1 `POST /admin/schools`

Creates a school **and its advisor account**, and issues the advisor's login hash.

```json
{
  "school_name": "Lincoln High School",
  "school_address": "1 Main St",
  "city": "San Jose",
  "state": "CA",
  "zip_code": "95112",
  "advisor_name": "Jane Doe",
  "advisor_phone": "555-0100",
  "advisor_email": "jane@lhs.edu",
  "head_delegate_name": "Alex Smith",
  "head_delegate_email": "alex@lhs.edu",
  "head_delegate_phone": "555-0101",
  "payment_status": "unpaid",
  "invoiceURL": null
}
```

Response `201`: `{ "id": 7, "name": "Lincoln High School", "advisor_hash": "8987407363cd1356" }`
— `id` is `schools.account_id`, i.e. the advisor's account id.

Field notes:
- **A school cannot exist without an advisor**: `schools.account_id` *is* its primary key. The
  advisor account is created with no password, so the advisor claims the hash through
  **First-Time Register** on the login screen — the same flow as a delegate. There is no
  separate "create advisor" step.
- `advisor_hash` is the only chance the admin is guaranteed to see the code; it is also
  returned by `GET /admin/schools` afterwards, so it can be recovered.
- `payment_status` is one of `paid`, `partially paid`, `unpaid` (default `unpaid`);
  `invoiceURL` is optional.
- `400` when a required detail is blank (the message names the fields), `409` when the
  school name is taken. Names are not merged: the name is what ties a school's delegates,
  papers and ticks together.
- Delegate hashes for the school come afterwards from `POST /admin/hashes`. Minting does
  **not** create a school; an unknown name is a `404` pointing here.

#### 8.7.2 `GET /admin/schools`

Response `200`:
`{ "schools": [ { "id": 7, "name": "Lincoln High School", "advisor_hash": "8987407363cd1356" } ] }`
— `id` is `schools.account_id`, `advisor_hash` is the advisor's login code (admin-only, so
unmasked). Used by the progress picker, the school list in the Hash Management tab, and by a
script that needs either the ids or the codes.

#### 8.7.3 `GET /admin/checklist`

The shared lines, in display order.

```json
{ "items": [ { "id": 3, "label": "Submit position papers" } ] }
```

#### 8.7.4 `PUT /admin/checklist`

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
- Response `200`: the saved lines, as in §8.7.3; `{"items": []}` clears the checklist for
  everyone. `400` for a blank, over-long or duplicate label, a repeated id, or more than 20
  lines; `404` for an unknown id.

#### 8.7.5 `GET /admin/schools/{id}/checklist`

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

#### 8.7.6 `PATCH /admin/schools/{id}/checklist`

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
- Response `200`: the school's checklist afterwards, as in §8.7.5.
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
| 1a | Auth | POST | `/auth/logout` | (204, no body) |
| 2 | Auth | POST | `/auth/register` | `{user, token}` |
| 3 | Delegate | GET | `/delegate/my-assignment` | dashboard object |
| 4 | Delegate | POST | `/delegate/upload-paper` | (ignored) |
| 5 | Delegate | GET | `/delegate/my-paper` | blob PDF |
| 6 | Advisor | GET | `/advisor/delegates` | `{delegates[], total}` |
| 7 | Advisor | GET | `/advisor/delegates/{id}/paper` | blob PDF |
| 8 | Advisor | POST | `/advisor/verify-hashes` | `{delegates[]}` |
| 9 | Advisor | GET | `/advisor/school` | `{school, billing, checklist}` |
| 10 | Chair | GET | `/chair/committee/overview` | overview object |
| 11 | Chair | GET | `/chair/rubric` | `[{id, label, maxScore}]` |
| 12 | Chair | GET | `/chair/delegates` | delegate array |
| 13 | Chair | POST | `/chair/papers/{id}/grade` | (ignored) |
| 14 | Chair | GET | `/chair/papers/{id}/download` | blob PDF |
| 15 | Chair | GET | `/chair/awards/options` | `[string]` |
| 16 | Chair | GET | `/chair/awards/rubric` | `[{id, label, levels[]}]` |
| 17 | Chair | GET | `/chair/awards/delegates` | delegate array |
| 18 | Chair | POST | `/chair/awards/{id}` | (ignored) |
| 19 | Admin | GET | `/admin/dashboard-stats` | stats object |
| 20 | Admin | GET | `/admin/ports/health` | port array |
| 21 | Admin | GET | `/admin/logs/business.txt` | blob text |
| 22 | Admin | GET | `/admin/logs/technology.txt` | blob text |
| 23 | Admin | GET | `/admin/export/database.csv` | blob CSV |
| 24 | Admin | POST | `/admin/hashes` | `{hashes[]}` |
| 25 | Admin | POST | `/admin/hashes/regenerate/delegate` | `{name, hash}` |
| 26 | Admin | POST | `/admin/hashes/regenerate/school` | `{hashes[]}` |
| 27 | Admin | DELETE | `/admin/hashes` | `{dropped[]}` |
| 28 | Admin | GET | `/admin/hashes?schoolName=` | `{hashes[]}` |
| 29 | Admin | GET | `/admin/awards` | `{committees[]}` |
| 30 | Admin | GET | `/admin/broadcasts?kind=` | `{broadcasts[]}` |
| 31 | Admin | POST | `/admin/broadcasts` | broadcast entry |
| 32 | Admin | PATCH | `/admin/broadcasts/{id}` | broadcast entry |
| 33 | Admin | DELETE | `/admin/broadcasts/{id}` | (204, no body) |
| 34 | Admin | GET | `/admin/committees` | `[string]` |
| 35 | Admin | GET | `/admin/schools` | `{schools[]}` |
| 35a | Admin | POST | `/admin/schools` | school entry incl. `advisor_hash` |
| 36 | Admin | GET | `/admin/checklist` | `{items[]}` |
| 37 | Admin | PUT | `/admin/checklist` | `{items[]}` |
| 38 | Admin | GET | `/admin/schools/{id}/checklist` | `{school_id, school_name, items[]}` |
| 39 | Admin | PATCH | `/admin/schools/{id}/checklist` | same as `GET` |
| 40 | Admin | GET | `/admin/timeline` | `{events[]}` |
| 41 | Admin | PUT | `/admin/timeline` | `{events[]}` |

**Roles** (from the router): `delegate`, `advisor`, `chair`, `admin`. Chair views also accept
`admin`.
