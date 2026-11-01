<template>
  <div class="admin-page">
    <header class="page-header">
      <h1>Admin Dashboard & Diagnostics</h1>
    </header>

    <!-- VIEW TOGGLE -->
    <div class="toggle-container">
      <button
        :class="['toggle-btn', { active: activeTab === 'diagnostics' }]"
        @click="switchTab('diagnostics')"
      >
        Diagnostics
      </button>
      <button
        :class="['toggle-btn', { active: activeTab === 'hashes' }]"
        @click="switchTab('hashes')"
      >
        Schools Management
      </button>
      <button
        :class="['toggle-btn', { active: activeTab === 'awards' }]"
        @click="switchTab('awards')"
      >
        Awards Overview
      </button>
      <button
        :class="['toggle-btn', { active: activeTab === 'content' }]"
        @click="switchTab('content')"
      >
        Delegate Content
      </button>
      <button
        :class="['toggle-btn', { active: activeTab === 'committees' }]"
        @click="switchTab('committees')"
      >
        Committees
      </button>
      <button
        :class="['toggle-btn', { active: activeTab === 'timeline' }]"
        @click="switchTab('timeline')"
      >
        Timeline
      </button>
    </div>

    <!-- ============================= DIAGNOSTICS ============================= -->
    <!-- Committee names, offered to every committee field in the page. A delegate can only
         be minted into a committee that exists, so the form suggests the real ones. -->
    <datalist id="committee-names">
      <option v-for="name in committeeNames" :key="name" :value="name"></option>
    </datalist>

    <template v-if="activeTab === 'diagnostics'">
      <!-- LOG & EXPORT ACTIONS -->
      <div class="section-card">
        <h2>Data & Log Exports</h2>
        <div class="action-buttons-grid">
          <button class="btn-action" @click="downloadFile('/admin/logs/business.txt', 'business-log.txt')">
            📄 Download Business Log (.txt)
          </button>
          <button class="btn-action" @click="downloadFile('/admin/logs/technology.txt', 'technology-log.txt')">
            🛠️ Download Technology Log (.txt)
          </button>
          <button class="btn-action btn-export" @click="downloadFile('/admin/export/database.csv', 'database-export.csv')">
            📊 Export Database (.csv)
          </button>
        </div>
      </div>

      <!-- METRICS GRID: DELEGATES & STORAGE -->
      <div class="metrics-grid">
        <!-- DELEGATE COUNTS -->
        <div class="section-card">
          <h2>Delegate Distribution</h2>
          <div class="total-badge">
            <span>Total Delegates</span>
            <strong>{{ totalDelegates }}</strong>
          </div>
          <div class="committee-list">
            <div
              v-for="item in committeeCounts"
              :key="item.committee"
              class="committee-item"
            >
              <span class="committee-name">{{ item.committee }}</span>
              <span class="committee-count">{{ item.count }} delegates</span>
            </div>
          </div>
        </div>

        <!-- STORAGE CAPACITY -->
        <div class="section-card">
          <h2>Server Storage</h2>
          <div class="storage-info">
            <div class="storage-values">
              <span>Disk Space Used</span>
              <strong>{{ storage.usedGb }} GB / {{ storage.totalGb }} GB</strong>
            </div>
            <div class="progress-bar-bg">
              <div
                class="progress-bar-fill"
                :style="{ width: storagePercentage + '%' }"
                :class="{ warning: storagePercentage > 80 }"
              ></div>
            </div>
            <div class="percentage-label">{{ storagePercentage }}% capacity utilized</div>
          </div>
        </div>
      </div>

      <!-- PORT HEALTH MONITOR -->
      <div class="section-card">
        <div class="card-header-action">
          <h2>Port Health Monitor</h2>
          <button class="btn-refresh" :disabled="checkingPorts" @click="fetchPortHealth">
            {{ checkingPorts ? 'Checking...' : '🔄 Check Port Health' }}
          </button>
        </div>

        <div class="ports-grid">
          <div
            v-for="port in ports"
            :key="port.port"
            :class="['port-card', port.status]"
          >
            <div class="port-info">
              <span class="port-name">{{ port.name }}</span>
              <span class="port-number">Port {{ port.port }}</span>
            </div>
            <span :class="['status-badge', port.status]">
              ● {{ port.status === 'healthy' ? 'Healthy' : 'Unreachable' }}
            </span>
          </div>
        </div>
      </div>

      <!-- DOWNTIME INCIDENT TIMELINE (PAST 7 DAYS) -->
      <div class="section-card">
        <h2>Server Downtime Log (Past 7 Days)</h2>
        <p class="section-desc">Recorded incidents where server health checks timed out or reported offline status.</p>

        <div v-if="downtimeEvents.length === 0" class="no-downtime">
          ✅ 100% Uptime — No downtime incidents recorded in the past 7 days.
        </div>

        <div v-else class="timeline-list">
          <div
            v-for="event in downtimeEvents"
            :key="event.id"
            class="timeline-item"
          >
            <div class="timeline-dot"></div>
            <div class="timeline-content">
              <div class="timeline-time">
                <strong>{{ event.startTime }}</strong> to <strong>{{ event.endTime }}</strong>
              </div>
              <div class="timeline-details">
                <span class="duration-badge">Duration: {{ event.duration }}</span>
                <span class="reason-text">{{ event.reason }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ============================ HASH MANAGEMENT ============================ -->
    <template v-if="activeTab === 'hashes'">
      <!-- CREATE A SCHOOL (and its advisor account) -->
      <div class="section-card">
        <h2>Create a School</h2>
        <p class="section-desc">
          Creates the school and its advisor account, and issues the advisor's login hash. The
          advisor claims it with "First-Time Register", exactly as a delegate does. Delegate
          hashes can be generated below once the school exists.
        </p>

        <div class="school-fields">
          <div class="field-pair">
            <label class="field-label" for="new-school-name">School name</label>
            <input id="new-school-name" v-model="newSchool.school_name" class="text-input" type="text" placeholder="e.g. Lincoln High School" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-address">Address</label>
            <input id="new-school-address" v-model="newSchool.school_address" class="text-input" type="text" placeholder="1 Main St" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-city">City</label>
            <input id="new-school-city" v-model="newSchool.city" class="text-input" type="text" placeholder="San Jose" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-state">State</label>
            <input id="new-school-state" v-model="newSchool.state" class="text-input" type="text" placeholder="CA" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-zip">ZIP</label>
            <input id="new-school-zip" v-model="newSchool.zip_code" class="text-input" type="text" placeholder="95112" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-payment">Payment status</label>
            <select id="new-school-payment" v-model="newSchool.payment_status" class="text-input">
              <option value="unpaid">unpaid</option>
              <option value="partially paid">partially paid</option>
              <option value="paid">paid</option>
            </select>
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-advisor">Advisor name</label>
            <input id="new-school-advisor" v-model="newSchool.advisor_name" class="text-input" type="text" placeholder="Jane Doe" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-advisor-email">Advisor email</label>
            <input id="new-school-advisor-email" v-model="newSchool.advisor_email" class="text-input" type="text" placeholder="jane@school.edu" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-advisor-phone">Advisor phone</label>
            <input id="new-school-advisor-phone" v-model="newSchool.advisor_phone" class="text-input" type="text" placeholder="555-0100" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-head">Head delegate</label>
            <input id="new-school-head" v-model="newSchool.head_delegate_name" class="text-input" type="text" placeholder="Alex Smith" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-head-email">Head delegate email</label>
            <input id="new-school-head-email" v-model="newSchool.head_delegate_email" class="text-input" type="text" placeholder="alex@school.edu" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-school-head-phone">Head delegate phone</label>
            <input id="new-school-head-phone" v-model="newSchool.head_delegate_phone" class="text-input" type="text" placeholder="555-0101" />
          </div>
        </div>

        <div class="row-actions">
          <button class="btn-refresh" :disabled="creatingSchool" @click="createSchool">
            {{ creatingSchool ? 'Creating...' : 'Create School & Issue Advisor Hash' }}
          </button>
        </div>

        <div v-if="createdSchool" class="hash-result">
          <h3>Advisor hash for {{ createdSchool.name }}</h3>
          <div class="hash-row">
            <span class="hash-name">{{ createdSchool.name }} — advisor</span>
            <span class="hash-value">{{ createdSchool.advisor_hash }}</span>
            <button class="btn-copy" @click="copyHash(createdSchool.advisor_hash)">Copy</button>
          </div>
          <p class="section-desc">
            Give this to the advisor. It is shown again in the school list below, and it cannot
            be reissued from here.
          </p>
        </div>

        <div v-if="schools.length" class="school-list">
          <h3>Schools</h3>
          <div v-for="school in schools" :key="school.id" class="school-block">
            <div class="hash-row">
              <span class="hash-name">{{ school.name }}</span>
              <span class="hash-value">{{ school.advisor_hash || 'no advisor hash' }}</span>
              <button v-if="school.advisor_hash" class="btn-copy" @click="copyHash(school.advisor_hash)">Copy</button>
              <button
                class="btn-copy"
                :disabled="generatingForSchool === school.id"
                title="Mints a hash for each delegate row you filled in below, for this school"
                @click="generateHashesForSchool(school)"
              >
                {{ generatingForSchool === school.id ? 'Generating…' : 'Issue delegate hashes' }}
              </button>
            </div>
            <div v-if="delegateHashesBySchool[school.id]" class="hash-result">
              <div v-for="entry in delegateHashesBySchool[school.id]" :key="entry.name" class="hash-row">
                <span class="hash-name">{{ entry.name }}</span>
                <span class="hash-value">{{ entry.hash }}</span>
                <button class="btn-copy" @click="copyHash(entry.hash)">Copy</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- CREATE + REGENERATE -->
      <div class="section-card">
        <h2>Generate Hashes for New Delegates</h2>
        <p class="section-desc">
          Register delegates for a school. Each row becomes an account and receives its own login hash.
        </p>

        <label class="field-label" for="school-name">School name</label>
        <input
          id="school-name"
          v-model="schoolName"
          class="text-input"
          type="text"
          placeholder="e.g. Lincoln High School"
        />

        <div class="form-rows">
          <div v-for="(row, index) in newDelegates" :key="index" class="form-row">
            <input v-model="row.committee" class="text-input" type="text" placeholder="Committee" list="committee-names" />
            <input v-model="row.committeeType" class="text-input" type="text" placeholder="Committee type" />
            <input v-model="row.country" class="text-input" type="text" placeholder="Country" />
            <button class="btn-icon" title="Remove row" @click="removeDelegateRow(index)">✕</button>
          </div>
        </div>

        <div class="row-actions">
          <button class="btn-secondary" @click="addDelegateRow">+ Add delegate</button>
          <button class="btn-refresh" :disabled="generatingHashes" @click="generateHashes">
            {{ generatingHashes ? 'Generating...' : 'Generate Hashes' }}
          </button>
        </div>

        <div v-if="generatedHashes.length" class="hash-result">
          <h3>New Hashes</h3>
          <div v-for="entry in generatedHashes" :key="entry.name" class="hash-row">
            <span class="hash-name">{{ entry.name }}</span>
            <span class="hash-value">{{ entry.hash }}</span>
            <button class="btn-copy" @click="copyHash(entry.hash)">Copy</button>
          </div>
        </div>
      </div>

      <!-- PICKER -->
      <div class="section-card">
        <h2>Existing Schools</h2>
        <p class="section-desc">
          Pick a school to see and edit everything attached to it. Only the selected school's
          data is loaded.
        </p>
        <label class="field-label" for="existing-school">School</label>
        <select
          id="existing-school"
          v-model="selectedSchoolId"
          class="text-input"
          @change="loadSchoolDetail"
        >
          <option :value="null">— choose a school —</option>
          <option v-for="school in schools" :key="school.id" :value="school.id">
            {{ school.name }}
          </option>
        </select>
        <div v-if="!schools.length" class="empty-state">
          No schools yet. Create one above.
        </div>
      </div>

      <!-- SCHOOL DETAILS -->
      <div v-if="schoolDetail" class="section-card">
        <div class="card-header-action">
          <h2>{{ schoolDetail.school.school_name }}</h2>
          <button
            class="btn-refresh"
            :disabled="!schoolDirty || savingSchool"
            @click="saveSchool"
          >
            {{ savingSchool ? 'Saving...' : 'Save changes' }}
          </button>
        </div>
        <p class="section-desc">
          Every field below is editable. The advisor hash is shown for reference; delegate
          hashes are reissued rather than typed.
        </p>

        <div class="school-fields">
          <div class="field-pair">
            <label class="field-label" for="edit-school-name">School name</label>
            <input id="edit-school-name" v-model="schoolDraft.school_name" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-address">Address</label>
            <input id="edit-school-address" v-model="schoolDraft.school_address" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-city">City</label>
            <input id="edit-school-city" v-model="schoolDraft.city" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-state">State</label>
            <input id="edit-school-state" v-model="schoolDraft.state" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-zip">ZIP</label>
            <input id="edit-school-zip" v-model="schoolDraft.zip_code" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-payment">Payment status</label>
            <select id="edit-school-payment" v-model="schoolDraft.payment_status" class="text-input">
              <option value="unpaid">unpaid</option>
              <option value="partially paid">partially paid</option>
              <option value="paid">paid</option>
            </select>
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-advisor">Advisor name</label>
            <input id="edit-school-advisor" v-model="schoolDraft.advisor_name" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-advisor-email">Advisor email</label>
            <input id="edit-school-advisor-email" v-model="schoolDraft.advisor_email" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-advisor-phone">Advisor phone</label>
            <input id="edit-school-advisor-phone" v-model="schoolDraft.advisor_phone" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-head">Head delegate</label>
            <input id="edit-school-head" v-model="schoolDraft.head_delegate_name" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-head-email">Head delegate email</label>
            <input id="edit-school-head-email" v-model="schoolDraft.head_delegate_email" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-head-phone">Head delegate phone</label>
            <input id="edit-school-head-phone" v-model="schoolDraft.head_delegate_phone" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-school-invoice">Invoice URL (optional)</label>
            <input id="edit-school-invoice" v-model="schoolDraft.invoiceURL" class="text-input" type="text" />
          </div>
        </div>

        <div class="hash-row">
          <span class="hash-name">Advisor hash</span>
          <span class="hash-value">{{ schoolDetail.advisor_hash || '—' }}</span>
          <button
            v-if="schoolDetail.advisor_hash"
            class="btn-copy"
            @click="copyHash(schoolDetail.advisor_hash)"
          >
            Copy
          </button>
        </div>

        <div class="row-actions">
          <button class="btn-danger" :disabled="deletingSchool" @click="deleteSchool">
            {{ deletingSchool ? 'Deleting...' : 'Delete this school' }}
          </button>
        </div>
      </div>

      <!-- DELEGATES -->
      <div v-if="schoolDetail" class="section-card">
        <h2>Delegates ({{ schoolDetail.delegates.length }})</h2>
        <p class="section-desc">
          Country and committee are editable — Save applies them. Reissuing a hash replaces the
          old one immediately.
        </p>

        <div v-if="!schoolDetail.delegates.length" class="empty-state">
          This school has no delegates yet.
        </div>
        <div v-else class="delegate-table">
          <div class="delegate-head">
            <span>Label</span>
            <span>Country</span>
            <span>Committee</span>
            <span>Paper</span>
            <span>Hash</span>
            <span></span>
          </div>
          <div v-for="row in delegateDrafts" :key="row.account_id" class="delegate-row">
            <span class="delegate-label">{{ row.name }}</span>
            <input v-model="row.country" class="text-input" type="text" />
            <input v-model="row.committee" class="text-input" type="text" />
            <span class="paper-badge" :class="'is-' + row.paper_status">
              {{ row.paper_status }}<template v-if="row.paper_grade"> · {{ row.paper_grade }}</template><template
                v-if="!row.has_paper && row.paper_status !== 'unsubmitted'"
              > (no file)</template>
            </span>
            <span class="hash-value">{{ row.hash }}</span>
            <div class="delegate-actions">
              <button
                class="btn-refresh"
                :disabled="!delegateDirty(row) || savingDelegateId === row.account_id"
                @click="saveDelegate(row)"
              >
                {{ savingDelegateId === row.account_id ? 'Saving...' : 'Save' }}
              </button>
              <button
                class="btn-copy"
                :disabled="reissuingId === row.account_id"
                @click="reissueHash(row)"
              >
                {{ reissuingId === row.account_id ? 'Reissuing...' : 'Reissue hash' }}
              </button>
            </div>
          </div>
        </div>
      </div>
      <!-- ALL HASHES (the old "Look Up Hashes" card, minus the filter) -->
      <div class="section-card">
        <div class="card-header-action">
          <h2>All Hashes</h2>
          <button class="btn-refresh" :disabled="loadingAllHashes" @click="loadAllHashes">
            {{ loadingAllHashes ? 'Loading...' : '🔄 Load all hashes' }}
          </button>
        </div>
        <p class="section-desc">
          Every delegate hash on one list, for a handout or a spot check. Individual hashes are
          reissued per delegate under Existing Schools above.
        </p>
        <div v-if="allHashes.length" class="hash-result">
          <div v-for="entry in allHashes" :key="entry.name" class="hash-row">
            <span class="hash-name">{{ entry.name }}</span>
            <span class="hash-value">{{ entry.hash }}</span>
            <button class="btn-copy" @click="copyHash(entry.hash)">Copy</button>
          </div>
        </div>
        <div v-else class="empty-state">
          {{ loadingAllHashes ? 'Loading hashes…' : 'No hashes loaded yet.' }}
        </div>
      </div>
    </template>

    <template v-if="activeTab === 'committees'">
      <!-- CREATE -->
      <div class="section-card">
        <h2>Create a Committee</h2>
        <p class="section-desc">
          A committee has to exist before its delegates can be minted — a delegate's committee
          is no longer created on the fly.
        </p>
        <div class="school-fields">
          <div class="field-pair">
            <label class="field-label" for="new-committee-name">Name</label>
            <input id="new-committee-name" v-model="newCommittee.committee_name" class="text-input" type="text" placeholder="e.g. DISEC" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-committee-type">Type (optional)</label>
            <input id="new-committee-type" v-model="newCommittee.committee_type" class="text-input" type="text" placeholder="e.g. General Assembly" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-committee-topic">Topic (optional)</label>
            <input id="new-committee-topic" v-model="newCommittee.topic" class="text-input" type="text" placeholder="e.g. Nuclear disarmament" />
          </div>
        </div>
        <div class="row-actions">
          <button class="btn-refresh" :disabled="creatingCommittee" @click="createCommittee">
            {{ creatingCommittee ? 'Creating...' : 'Create Committee' }}
          </button>
        </div>
      </div>

      <!-- PICKER -->
      <div class="section-card">
        <h2>Existing Committees</h2>
        <p class="section-desc">Pick a committee to see its chairs and delegates.</p>
        <label class="field-label" for="committee-picker">Committee</label>
        <select id="committee-picker" v-model="selectedCommittee" class="text-input" @change="loadCommitteeDetail">
          <option value="">— choose a committee —</option>
          <option v-for="name in committeeNames" :key="name" :value="name">{{ name }}</option>
        </select>
        <div v-if="!committeeNames.length" class="empty-state">
          No committees yet — create one above.
        </div>
      </div>

      <!-- DETAILS -->
      <div v-if="committeeDetail" class="section-card">
        <div class="card-header-action">
          <h2>{{ committeeDetail.committee_name }}</h2>
          <button class="btn-refresh" :disabled="!committeeDirty || savingCommittee" @click="saveCommittee">
            {{ savingCommittee ? 'Saving...' : 'Save changes' }}
          </button>
        </div>
        <p class="section-desc">
          Renaming repoints every delegate, chair and committee-scoped announcement at the new
          name in one step.
        </p>
        <div class="school-fields">
          <div class="field-pair">
            <label class="field-label" for="edit-committee-name">Name</label>
            <input id="edit-committee-name" v-model="committeeDraft.committee_name" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-committee-type">Type</label>
            <input id="edit-committee-type" v-model="committeeDraft.committee_type" class="text-input" type="text" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="edit-committee-topic">Topic</label>
            <input id="edit-committee-topic" v-model="committeeDraft.topic" class="text-input" type="text" />
          </div>
        </div>
      </div>

      <!-- CHAIRS -->
      <div v-if="committeeDetail" class="section-card">
        <h2>Chairs ({{ committeeDetail.chairs.length }})</h2>
        <p class="section-desc">
          Each chair signs up with their hash using "First-Time Register". Reissuing a hash
          invalidates the old one immediately.
        </p>

        <div v-if="!committeeDetail.chairs.length" class="empty-state">No chairs assigned yet.</div>
        <div v-else class="chair-table">
          <div class="chair-head">
            <span>Name</span><span>Email</span><span>Hash</span><span></span>
          </div>
          <div v-for="row in chairDrafts" :key="row.account_id" class="chair-row">
            <input v-model="row.name" class="text-input" type="text" />
            <input v-model="row.email" class="text-input" type="text" />
            <span class="hash-value">{{ row.hash }}</span>
            <div class="delegate-actions">
              <button class="btn-refresh" :disabled="!chairDirty(row) || savingChairId === row.account_id" @click="saveChair(row)">
                {{ savingChairId === row.account_id ? 'Saving...' : 'Save' }}
              </button>
              <button class="btn-copy" @click="copyHash(row.hash)">Copy</button>
              <button class="btn-copy" :disabled="reissuingChairId === row.account_id" @click="reissueChair(row)">
                {{ reissuingChairId === row.account_id ? 'Reissuing...' : 'Reissue' }}
              </button>
              <button class="btn-copy btn-copy-danger" :disabled="removingChairId === row.account_id" @click="removeChair(row)">
                {{ removingChairId === row.account_id ? 'Removing...' : 'Remove' }}
              </button>
            </div>
          </div>
        </div>

        <div class="school-fields chair-add">
          <div class="field-pair">
            <label class="field-label" for="new-chair-name">New chair name</label>
            <input id="new-chair-name" v-model="newChair.name" class="text-input" type="text" placeholder="Jane Doe" />
          </div>
          <div class="field-pair">
            <label class="field-label" for="new-chair-email">New chair email</label>
            <input id="new-chair-email" v-model="newChair.email" class="text-input" type="text" placeholder="jane@lhs.edu" />
          </div>
        </div>
        <div class="row-actions">
          <button class="btn-refresh" :disabled="addingChair" @click="addChair">
            {{ addingChair ? 'Adding...' : 'Add chair & issue hash' }}
          </button>
        </div>
      </div>

      <!-- DELEGATES -->
      <div v-if="committeeDetail" class="section-card">
        <h2>Delegates ({{ committeeDetail.delegates.length }})</h2>
        <p class="section-desc">
          Country and committee edits live in Existing Schools; here you can reissue a hash or
          remove the delegate from this committee entirely.
        </p>

        <div v-if="!committeeDetail.delegates.length" class="empty-state">
          No delegates in this committee yet.
        </div>
        <div v-else class="delegate-table">
          <div class="delegate-head">
            <span>School</span><span>Country</span><span>Paper</span><span>Hash</span><span></span>
          </div>
          <div v-for="row in committeeDetail.delegates" :key="row.account_id" class="delegate-row committee-row">
            <span class="delegate-label">{{ row.school_name }}</span>
            <span>{{ row.country }}</span>
            <span class="paper-badge" :class="'is-' + row.paper_status">
              {{ row.paper_status }}<template v-if="row.paper_grade"> · {{ row.paper_grade }}</template><template
                v-if="!row.has_paper && row.paper_status !== 'unsubmitted'"
              > (no file)</template>
            </span>
            <span class="hash-value">{{ row.hash }}</span>
            <div class="delegate-actions">
              <button class="btn-copy" @click="copyHash(row.hash)">Copy</button>
              <button class="btn-copy" :disabled="reissuingDelegateId === row.account_id" @click="reissueCommitteeDelegate(row)">
                {{ reissuingDelegateId === row.account_id ? 'Reissuing...' : 'Reissue' }}
              </button>
              <button class="btn-copy btn-copy-danger" :disabled="removingDelegateId === row.account_id" @click="removeCommitteeDelegate(row)">
                {{ removingDelegateId === row.account_id ? 'Removing...' : 'Remove' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-if="activeTab === 'awards'">
      <div class="section-card">
        <div class="card-header-action">
          <h2>Conference Awards Overview</h2>
          <button class="btn-refresh" :disabled="loadingAwards" @click="loadAwards">
            {{ loadingAwards ? 'Loading...' : '🔄 Reload' }}
          </button>
        </div>
        <p class="section-desc">
          Read-only report of every committee's award assignments.
        </p>

        <div v-if="awardsCommittees.length" class="committee-awards-list">
          <div v-for="committee in awardsCommittees" :key="committee.committee" class="awards-card">
            <h3>{{ committee.committee }}</h3>
            <div v-for="entry in committee.awards" :key="entry.country" class="award-row">
              <span class="award-country">{{ entry.country }}</span>
              <span class="award-name">{{ entry.award }}</span>
            </div>
            <div v-if="!committee.awards.length" class="empty-state">No awards assigned.</div>
          </div>
        </div>
        <div v-else class="empty-state">No award data available.</div>
      </div>
    </template>

    <!-- ==================== ANNOUNCEMENTS & CONFERENCE LINKS ==================== -->
    <template v-if="activeTab === 'content'">
      <!-- EDITOR -->
      <div class="section-card">
        <h2>Announcements &amp; Conference Links</h2>
        <p class="section-desc">
          What delegates see on their dashboard: announcements fill the bar at the top
          (up to 3 lines), links fill the five slots in the "Conference &amp; General Info"
          panel. A line addressed to a committee reaches only that committee's delegates,
          and is shown after the general lines.
        </p>

        <div class="toggle-container">
          <button
            v-for="option in broadcastKinds"
            :key="option.kind"
            :class="['toggle-btn', { active: broadcastKind === option.kind }]"
            @click="selectBroadcastKind(option.kind)"
          >
            {{ option.label }}
          </button>
        </div>

        <p class="capacity-line">
          <strong>Space left:</strong>
          <span
            v-for="row in broadcastCapacity"
            :key="row.label"
            :class="['capacity-chip', { full: row.full }]"
          >
            {{ row.label }}: {{ row.used }}/{{ row.limit }}
          </span>
          <span class="capacity-note">
            counted per target, and a line that has not ended yet still holds its place
          </span>
        </p>

        <div class="broadcast-form">
          <label class="field-label" :for="`broadcast-body`">{{ broadcastBodyLabel }}</label>
          <input
            id="broadcast-body"
            v-model="newBroadcast.body"
            class="text-input"
            type="text"
            :placeholder="broadcastBodyPlaceholder"
          />

          <template v-if="broadcastKind === 'link'">
            <label class="field-label" for="broadcast-url">Link URL</label>
            <input
              id="broadcast-url"
              v-model="newBroadcast.url"
              class="text-input"
              type="text"
              placeholder="https://..."
            />
          </template>

          <label class="field-label" for="broadcast-target">Shown to</label>
          <select id="broadcast-target" v-model="newBroadcast.committee_name" class="text-input">
            <option :value="null">All delegates</option>
            <option v-for="committee in committees" :key="committee" :value="committee">
              {{ committee }}
            </option>
          </select>

          <div class="schedule-row">
            <div>
              <label class="field-label" for="broadcast-starts">Starts (optional)</label>
              <input
                id="broadcast-starts"
                v-model="newBroadcast.starts_at"
                class="text-input"
                type="datetime-local"
              />
            </div>
            <div>
              <label class="field-label" for="broadcast-ends">Ends (optional)</label>
              <input
                id="broadcast-ends"
                v-model="newBroadcast.ends_at"
                class="text-input"
                type="datetime-local"
              />
            </div>
          </div>
          <p class="capacity-note">
            Times are your local time. Leave both blank to publish now with no end.
          </p>

          <div class="row-actions">
            <button
              class="btn-refresh"
              :disabled="savingBroadcast || targetFull"
              @click="createBroadcast"
            >
              {{ savingBroadcast ? 'Saving...' : 'Publish' }}
            </button>
            <span v-if="targetFull" class="capacity-warning">
              That target is full — delete one of its lines first.
            </span>
          </div>
        </div>
      </div>

      <!-- PUBLISHED LIST -->
      <div class="section-card">
        <div class="card-header-action">
          <h2>{{ broadcastKind === 'link' ? 'Conference Links' : 'Announcements' }}</h2>
          <button class="btn-refresh" :disabled="loadingBroadcasts" @click="loadBroadcasts">
            {{ loadingBroadcasts ? 'Loading...' : '🔄 Reload' }}
          </button>
        </div>
        <p class="section-desc">
          Use ▲ ▼ to reorder within a target. General lines are always shown before
          committee lines, whatever their position.
        </p>

        <div v-if="!broadcastsOfKind.length" class="empty-state">
          Nothing published yet.
        </div>

        <div v-for="group in broadcastGroups" :key="group.label" class="broadcast-group">
          <h3>{{ group.label }}</h3>

          <div
            v-for="row in group.rows"
            :key="row.id"
            :class="['broadcast-row', { editing: editingId === row.id }]"
          >
            <!-- EDIT MODE -->
            <template v-if="editingId === row.id">
              <input v-model="editDraft.body" class="text-input" type="text" />
              <input
                v-if="row.kind === 'link'"
                v-model="editDraft.url"
                class="text-input"
                type="text"
                placeholder="https://..."
              />
              <select v-model="editDraft.committee_name" class="text-input">
                <option :value="null">All delegates</option>
                <option v-for="committee in committees" :key="committee" :value="committee">
                  {{ committee }}
                </option>
              </select>
              <div class="schedule-row">
                <input v-model="editDraft.starts_at" class="text-input" type="datetime-local" />
                <input v-model="editDraft.ends_at" class="text-input" type="datetime-local" />
              </div>
              <div class="row-actions">
                <button class="btn-refresh" :disabled="savingBroadcast" @click="saveBroadcast(row)">
                  {{ savingBroadcast ? 'Saving...' : 'Save' }}
                </button>
                <button class="btn-secondary" @click="cancelEdit">Cancel</button>
              </div>
            </template>

            <!-- READ MODE -->
            <template v-else>
              <div class="broadcast-main">
                <span class="broadcast-body">{{ row.body }}</span>
                <span v-if="row.url" class="broadcast-url">{{ row.url }}</span>
                <span class="broadcast-schedule">{{ scheduleLabel(row) }}</span>
              </div>
              <span :class="['broadcast-state', stateClass(row)]">{{ stateLabel(row) }}</span>
              <div class="broadcast-actions">
                <button
                  class="btn-icon"
                  title="Move up"
                  :disabled="!canMove(row, -1) || savingBroadcast"
                  @click="moveBroadcast(row, -1)"
                >
                  ▲
                </button>
                <button
                  class="btn-icon"
                  title="Move down"
                  :disabled="!canMove(row, 1) || savingBroadcast"
                  @click="moveBroadcast(row, 1)"
                >
                  ▼
                </button>
                <button class="btn-secondary" @click="startEdit(row)">Edit</button>
                <button class="btn-danger" :disabled="savingBroadcast" @click="deleteBroadcast(row)">
                  Delete
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- CONFERENCE CHECKLIST: SHARED LABELS -->
      <div class="section-card">
        <h2>Conference Action Checklist</h2>
        <p class="section-desc">
          The checklist lines shown on <strong>every</strong> advisor's dashboard — the labels
          are shared, the ticks are per school (below). Add, rename or remove lines; Save
          replaces the whole list. Removing a line also removes every school's tick for it.
        </p>

        <p v-if="loadingChecklist" class="section-desc">Loading checklist…</p>

        <template v-else>
          <div v-if="!checklistItems.length" class="empty-state">
            No lines yet — add the first one below.
          </div>

          <div v-for="(item, index) in checklistItems" :key="index" class="checklist-row">
            <input
              v-model="item.label"
              class="text-input"
              type="text"
              placeholder="e.g. Submit position papers"
              @input="checklistDirty = true"
            />
            <button class="btn-icon" title="Remove line" @click="removeChecklistItem(index)">✕</button>
          </div>

          <div class="row-actions">
            <button
              class="btn-secondary"
              :disabled="checklistItems.length >= maxChecklistItems"
              @click="addChecklistItem"
            >
              + Add line
            </button>
            <button
              class="btn-refresh"
              :disabled="savingChecklist || !checklistDirty"
              @click="saveChecklist"
            >
              {{ savingChecklist ? 'Saving...' : 'Save checklist' }}
            </button>
            <span v-if="checklistDirty" class="capacity-warning">Unsaved changes</span>
            <span class="capacity-note">{{ checklistItems.length }}/{{ maxChecklistItems }} lines</span>
          </div>
        </template>
      </div>

      <!-- CHECKLIST PROGRESS: PER SCHOOL -->
      <div class="section-card">
        <h2>Checklist Progress</h2>
        <p class="section-desc">
          Which lines a school has ticked. Pick a school and tick its boxes — a tick here
          shows only on that school's advisor dashboard.
        </p>

        <label class="field-label" for="progress-school">School</label>
        <select
          id="progress-school"
          v-model="progressSchoolId"
          class="text-input"
          @change="onProgressSchoolChange"
        >
          <option :value="null">Select a school…</option>
          <option v-for="school in schools" :key="school.id" :value="school.id">
            {{ school.name }}
          </option>
        </select>

        <template v-if="progressSchoolId !== null">
          <p v-if="loadingProgress" class="section-desc">Loading progress…</p>

          <template v-else>
            <p v-if="!progressItems.length" class="empty-state">
              No checklist lines to tick yet — add some above and save first.
            </p>

            <div v-for="item in progressItems" :key="item.id" class="checklist-row">
              <input
                v-model="item.completed"
                type="checkbox"
                :title="item.completed ? 'Done' : 'Outstanding'"
                @change="progressDirty = true"
              />
              <span class="progress-label">{{ item.label }}</span>
            </div>

            <div class="row-actions">
              <button
                class="btn-refresh"
                :disabled="savingProgress || !progressDirty"
                @click="saveProgress"
              >
                {{ savingProgress ? 'Saving...' : 'Save progress' }}
              </button>
              <span v-if="progressDirty" class="capacity-warning">Unsaved changes</span>
              <span class="capacity-note">{{ progressDone }}/{{ progressItems.length }} ticked</span>
            </div>
          </template>
        </template>
      </div>
    </template>

    <!-- ============================== TIMELINE ============================== -->
    <template v-if="activeTab === 'timeline'">
      <div class="section-card">
        <div class="card-header-action">
          <h2>Conference Timeline</h2>
          <button class="btn-refresh" :disabled="loadingTimeline" @click="loadTimeline">
            {{ loadingTimeline ? 'Loading...' : '🔄 Reload' }}
          </button>
        </div>
        <p class="section-desc">
          The schedule every chair sees on their committee overview. Events are
          <strong>points in time</strong> — a chair's dashboard marks each one completed, in
          progress or upcoming by comparing it with the clock, so there is nothing to tick.
          Order does not matter here: the list is sorted by time when it is saved.
        </p>

        <div v-if="!timelineEvents.length" class="empty-state">
          No events yet — add the first one below.
        </div>

        <div v-for="(event, index) in timelineEvents" :key="index" class="timeline-editor-row">
          <select v-model="event.phase" class="text-input" @change="timelineDirty = true">
            <option v-for="phase in timelinePhases" :key="phase.value" :value="phase.value">
              {{ phase.label }}
            </option>
          </select>
          <input
            v-model="event.label"
            class="text-input"
            type="text"
            placeholder="e.g. Opening Ceremony"
            @input="timelineDirty = true"
          />
          <input
            v-model="event.starts_at"
            class="text-input"
            type="datetime-local"
            @input="timelineDirty = true"
          />
          <button class="btn-icon" title="Remove event" @click="removeTimelineEvent(index)">✕</button>
        </div>

        <div class="row-actions">
          <button
            class="btn-secondary"
            :disabled="timelineEvents.length >= maxTimelineEvents"
            @click="addTimelineEvent"
          >
            + Add event
          </button>
          <button
            class="btn-refresh"
            :disabled="savingTimeline || !timelineDirty"
            @click="saveTimeline"
          >
            {{ savingTimeline ? 'Saving...' : 'Save timeline' }}
          </button>
          <span v-if="timelineDirty" class="capacity-warning">Unsaved changes</span>
          <span class="capacity-note">
            {{ timelineEvents.length }}/{{ maxTimelineEvents }} events · times are your local time
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import apiClient from '@/api/client'
import { useToastStore } from '@/stores/toast'

const toastStore = useToastStore()

// Active tab: 'diagnostics' | 'hashes' | 'committees' | 'awards' | 'content' | 'timeline'
const activeTab = ref('diagnostics')

// ---------- Diagnostics state ----------
const totalDelegates = ref(0)
const committeeCounts = ref([])
const storage = ref({ usedGb: 0, totalGb: 0 })
const ports = ref([])
const downtimeEvents = ref([])
const checkingPorts = ref(false)

// ---------- Hash management state ----------
const schoolName = ref('')

// ---------- Create a school (POST /admin/schools) ----------
const emptySchool = () => ({
  school_name: '',
  school_address: '',
  city: '',
  state: '',
  zip_code: '',
  payment_status: 'unpaid',
  advisor_name: '',
  advisor_email: '',
  advisor_phone: '',
  head_delegate_name: '',
  head_delegate_email: '',
  head_delegate_phone: ''
})

const newSchool = ref(emptySchool())
const creatingSchool = ref(false)
const createdSchool = ref(null)

// Per-school delegate hashes, keyed by school id, plus which row is mid-request.
const delegateHashesBySchool = ref({})
const generatingForSchool = ref(null)

const createSchool = async () => {
  const required = [
    ['school_name', 'school name'],
    ['school_address', 'address'],
    ['city', 'city'],
    ['state', 'state'],
    ['zip_code', 'ZIP code'],
    ['advisor_name', 'advisor name'],
    ['advisor_email', 'advisor email'],
    ['advisor_phone', 'advisor phone'],
    ['head_delegate_name', 'head delegate name'],
    ['head_delegate_email', 'head delegate email'],
    ['head_delegate_phone', 'head delegate phone']
  ]
  const missing = required.filter(([key]) => !String(newSchool.value[key] || '').trim())
  if (missing.length) {
    toastStore.showToast(
      `Please fill in: ${missing.map(([, label]) => label).join(', ')}.`,
      'error'
    )
    return
  }

  creatingSchool.value = true
  try {
    const response = await apiClient.post('/admin/schools', newSchool.value)
    createdSchool.value = response.data
    newSchool.value = emptySchool()
    // The school must show up in the progress picker and in the list above.
    await loadSchools()
    toastStore.showToast(`${response.data.name} created — advisor hash issued.`, 'success')
  } catch (error) {
    // 409 for a duplicate name and the 400s come through the global toast interceptor
  } finally {
    creatingSchool.value = false
  }
}
const newDelegates = ref([{ committee: '', committeeType: '', country: '' }])
const generatingHashes = ref(false)
const generatedHashes = ref([])

const allHashes = ref([])
const loadingAllHashes = ref(false)

// ---------- Awards state ----------
const awardsCommittees = ref([])
const loadingAwards = ref(false)

// ---------- Announcements & conference links state ----------
const broadcastKinds = [
  { kind: 'announcement', label: 'Announcements' },
  { kind: 'link', label: 'Conference Links' }
]

// Mirror of core.controls.BROADCAST_LIMITS in the backend, used to show capacity.
// The backend is still the authority: it returns 409 if a create would overflow.
const broadcastLimits = {
  announcement: { global: 2, committee: 1 },
  link: { global: 2, committee: 3 }
}

const broadcastKind = ref('announcement')
const broadcasts = ref([])
const committees = ref([])
const loadingBroadcasts = ref(false)
const savingBroadcast = ref(false)
const editingId = ref(null)

const emptyBroadcast = () => ({ body: '', url: '', committee_name: null, starts_at: '', ends_at: '' })
const newBroadcast = ref(emptyBroadcast())
const editDraft = ref(emptyBroadcast())

// ---------- Conference checklist state (shared labels) ----------
const checklistItems = ref([])
const loadingChecklist = ref(false)
const savingChecklist = ref(false)
const checklistDirty = ref(false)
const maxChecklistItems = 20 // mirrors MAX_CHECKLIST_ITEMS in admin.py

// ---------- Checklist progress state (per school) ----------
const schools = ref([])
const progressSchoolId = ref(null)
const savedProgressSchoolId = ref(null) // the school the tick draft belongs to
const progressItems = ref([])
const loadingProgress = ref(false)
const savingProgress = ref(false)
const progressDirty = ref(false)

// ---------- Timeline state ----------
const timelinePhases = [
  { value: 'preConference', label: 'Pre-conference' },
  { value: 'duringConference', label: 'During conference' }
]
const timelineEvents = ref([])
const loadingTimeline = ref(false)
const savingTimeline = ref(false)
const timelineDirty = ref(false)
const maxTimelineEvents = 30 // mirrors MAX_TIMELINE_EVENTS in admin.py

// ---------- Computed ----------
const storagePercentage = computed(() => {
  if (!storage.value.totalGb) return 0
  return Number(((storage.value.usedGb / storage.value.totalGb) * 100).toFixed(1))
})

const progressDone = computed(
  () => progressItems.value.filter((item) => item.completed).length
)

// ---------- Broadcast computed ----------
const broadcastsOfKind = computed(() =>
  broadcasts.value.filter((row) => row.kind === broadcastKind.value)
)

const broadcastBodyLabel = computed(() =>
  broadcastKind.value === 'link' ? 'Link label' : 'Announcement text'
)

const broadcastBodyPlaceholder = computed(() =>
  broadcastKind.value === 'link'
    ? 'e.g. Conference schedule'
    : 'e.g. Buses depart the hotel at 7:30am'
)

// Rows that can still be shown: one that has already ended releases its place.
const countsTowardCapacity = (row) => !row.ends_at || Date.parse(`${row.ends_at}Z`) > Date.now()

const usedFor = (kind, committeeName) =>
  broadcasts.value.filter(
    (row) =>
      row.kind === kind &&
      (row.committee_name ?? null) === (committeeName ?? null) &&
      countsTowardCapacity(row)
  ).length

// Capacity for the general target plus whichever target the form is pointing at.
const broadcastCapacity = computed(() => {
  const limits = broadcastLimits[broadcastKind.value]
  const targets = [{ label: 'All delegates', key: null, limit: limits.global }]
  const selected = newBroadcast.value.committee_name
  if (selected) {
    targets.push({ label: selected, key: selected, limit: limits.committee })
  }
  return targets.map((target) => {
    const used = usedFor(broadcastKind.value, target.key)
    return { label: target.label, used, limit: target.limit, full: used >= target.limit }
  })
})

const targetFull = computed(() => {
  const limits = broadcastLimits[broadcastKind.value]
  const selected = newBroadcast.value.committee_name
  const limit = selected ? limits.committee : limits.global
  return usedFor(broadcastKind.value, selected) >= limit
})

// One group per target, so reordering only competes with lines the delegate sees together.
const broadcastGroups = computed(() => {
  const byPosition = (a, b) => a.position - b.position || a.id - b.id
  const rows = broadcastsOfKind.value
  const groups = []

  const general = rows.filter((row) => !row.committee_name).sort(byPosition)
  if (general.length) groups.push({ label: 'All delegates', rows: general })

  committees.value.forEach((committee) => {
    const targeted = rows.filter((row) => row.committee_name === committee).sort(byPosition)
    if (targeted.length) groups.push({ label: committee, rows: targeted })
  })

  const known = new Set([null, ...committees.value])
  const orphans = rows.filter((row) => !known.has(row.committee_name)).sort(byPosition)
  if (orphans.length) groups.push({ label: 'Other committees', rows: orphans })

  return groups
})

// ---------- Tab switching (lazy-loads the data each tab needs) ----------
const switchTab = (tab) => {
  activeTab.value = tab
  editingId.value = null
  if (tab === 'hashes' && schools.value.length === 0) {
    loadSchools()
  }
  if (tab === 'committees' && committeeNames.value.length === 0) {
    loadCommittees()
  }
  if (tab === 'hashes' && committeeNames.value.length === 0) {
    loadCommittees()
  }
  if (tab === 'awards' && awardsCommittees.value.length === 0) {
    loadAwards()
  }
  if (tab === 'content' && broadcasts.value.length === 0) {
    loadBroadcasts()
  }
  // Refreshed on entry, but never over unsaved edits.
  if (tab === 'content' && !checklistDirty.value) {
    loadChecklist()
  }
  if (tab === 'content' && schools.value.length === 0) {
    loadSchools()
  }
  // Refreshed on entry, but never over unsaved edits.
  if (tab === 'timeline' && !timelineDirty.value) {
    loadTimeline()
  }
}

// ---------- Diagnostics helpers ----------
// Fetches secure files/logs as a blob and hands them to the browser as a download.
const downloadFile = async (endpoint, fileName) => {
  try {
    const response = await apiClient.get(endpoint, {
      responseType: 'blob' // Essential for binary/text file downloads
    })

    const blob = new Blob([response.data])
    const url = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = fileName
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    window.URL.revokeObjectURL(url)
  } catch (error) {
    toastStore.showToast(`Failed to download ${fileName}.`, 'error')
  }
}

const fetchPortHealth = async () => {
  checkingPorts.value = true

  try {
    const response = await apiClient.get('/admin/ports/health')
    ports.value = response.data
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    checkingPorts.value = false
  }
}

// ---------- Hash management actions ----------
const addDelegateRow = () => {
  newDelegates.value.push({ committee: '', committeeType: '', country: '' })
}

const removeDelegateRow = (index) => {
  if (newDelegates.value.length === 1) {
    newDelegates.value[0] = { committee: '', committeeType: '', country: '' }
    return
  }
  newDelegates.value.splice(index, 1)
}

// The delegate rows entered in the card below, keyed by position ("1", "2"); each value is
// [committee, type, country]. The school travels separately as `school_name`, and the
// backend labels every entry "<school> - #<n>" for display. Shared by both entry points so
// there is one definition of what gets submitted.
const buildAssignments = () => {
  const finalAssignments = {}
  newDelegates.value.forEach((row, index) => {
    if (!row.committee.trim() && !row.committeeType.trim() && !row.country.trim()) return
    finalAssignments[`${index + 1}`] = [
      row.committee.trim(),
      row.committeeType.trim(),
      row.country.trim()
    ]
  })
  return finalAssignments
}

// POST /admin/hashes for one school name. Returns null when there is nothing to send, so
// callers can bail without treating it as an error; real failures throw.
const requestHashes = async (school) => {
  const finalAssignments = buildAssignments()
  if (Object.keys(finalAssignments).length === 0) {
    toastStore.showToast('Add at least one delegate row first.', 'error')
    return null
  }
  const response = await apiClient.post('/admin/hashes', { school_name: school, finalAssignments })
  return response.data.hashes || []
}

const generateHashes = async () => {
  const school = schoolName.value.trim()
  if (!school) {
    toastStore.showToast('Enter a school name before generating hashes.', 'error')
    return
  }

  generatingHashes.value = true
  try {
    const hashes = await requestHashes(school)
    if (hashes === null) return
    generatedHashes.value = hashes
    toastStore.showToast('Hashes generated.', 'success')
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    generatingHashes.value = false
  }
}

// Issued from the school list: the school name comes from the row, the delegates from the
// rows below. Results are stored per school so they appear where the button was clicked.
const generateHashesForSchool = async (school) => {
  generatingForSchool.value = school.id
  try {
    const hashes = await requestHashes(school.name)
    if (hashes === null) return
    delegateHashesBySchool.value = { ...delegateHashesBySchool.value, [school.id]: hashes }
    toastStore.showToast(`${hashes.length} hash(es) issued for ${school.name}.`, 'success')
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    generatingForSchool.value = null
  }
}

const loadAllHashes = async () => {
  loadingAllHashes.value = true
  try {
    // No schoolName filter: the endpoint returns every delegate hash when it is omitted.
    const response = await apiClient.get('/admin/hashes')
    allHashes.value = response.data.hashes || []
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    loadingAllHashes.value = false
  }
}

const copyHash = async (hash) => {
  try {
    await navigator.clipboard.writeText(hash)
    toastStore.showToast('Hash copied to clipboard.', 'success')
  } catch (error) {
    toastStore.showToast('Could not copy the hash.', 'error')
  }
}

// ---------- Awards actions ----------
const loadAwards = async () => {
  loadingAwards.value = true
  try {
    const response = await apiClient.get('/admin/awards')
    awardsCommittees.value = response.data.committees
  } catch (error) {
    // Errors automatically pop up via global toast interceptor
  } finally {
    loadingAwards.value = false
  }
}

// ---------- Broadcast helpers ----------
// The API stores naive UTC; <input type="datetime-local"> speaks local wall-clock time,
// so every value crosses that boundary through these two helpers.
const toLocalInput = (iso) => {
  if (!iso) return ''
  const date = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value) => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

const toUtcIso = (local) => {
  if (!local) return null
  const date = new Date(local)
  if (Number.isNaN(date.getTime())) return null
  return date.toISOString().slice(0, 19) // drop the trailing Z: the API wants naive UTC
}

const formatLocal = (iso) => {
  if (!iso) return ''
  const date = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

const scheduleLabel = (row) =>
  `${row.starts_at ? `from ${formatLocal(row.starts_at)}` : 'from now'} · ${
    row.ends_at ? `until ${formatLocal(row.ends_at)}` : 'no end'
  }`

const stateLabel = (row) => {
  const now = Date.now()
  if (row.ends_at && Date.parse(`${row.ends_at}Z`) <= now) return 'Ended'
  if (row.starts_at && Date.parse(`${row.starts_at}Z`) > now) return 'Scheduled'
  return 'Live'
}

const stateClass = (row) => stateLabel(row).toLowerCase()

const nextPosition = (kind, committeeName) => {
  const group = broadcasts.value.filter(
    (row) => row.kind === kind && (row.committee_name ?? null) === (committeeName ?? null)
  )
  return group.length ? Math.max(...group.map((row) => row.position)) + 1 : 0
}

const groupOf = (row) =>
  broadcasts.value
    .filter(
      (other) =>
        other.kind === row.kind && (other.committee_name ?? null) === (row.committee_name ?? null)
    )
    .sort((a, b) => a.position - b.position || a.id - b.id)

const canMove = (row, delta) => {
  const group = groupOf(row)
  const index = group.findIndex((other) => other.id === row.id)
  return index + delta >= 0 && index + delta < group.length
}

// ---------- Broadcast actions ----------
const loadBroadcasts = async () => {
  loadingBroadcasts.value = true
  try {
    const [listResponse, committeeResponse] = await Promise.all([
      apiClient.get('/admin/broadcasts'),
      apiClient.get('/admin/committees')
    ])
    broadcasts.value = listResponse.data.broadcasts || []
    committees.value = committeeResponse.data || []
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingBroadcasts.value = false
  }
}

const selectBroadcastKind = (kind) => {
  broadcastKind.value = kind
  editingId.value = null
  newBroadcast.value = emptyBroadcast()
}

const createBroadcast = async () => {
  if (!newBroadcast.value.body.trim()) {
    toastStore.showToast('Enter the text before publishing.', 'error')
    return
  }

  savingBroadcast.value = true
  try {
    await apiClient.post('/admin/broadcasts', {
      kind: broadcastKind.value,
      body: newBroadcast.value.body,
      url: broadcastKind.value === 'link' ? newBroadcast.value.url : null,
      committee_name: newBroadcast.value.committee_name,
      position: nextPosition(broadcastKind.value, newBroadcast.value.committee_name),
      starts_at: toUtcIso(newBroadcast.value.starts_at),
      ends_at: toUtcIso(newBroadcast.value.ends_at)
    })
    newBroadcast.value = emptyBroadcast()
    toastStore.showToast('Published.', 'success')
    await loadBroadcasts()
  } catch (error) {
    // 409 (target full) and validation errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

const startEdit = (row) => {
  editingId.value = row.id
  editDraft.value = {
    body: row.body,
    url: row.url || '',
    committee_name: row.committee_name,
    starts_at: toLocalInput(row.starts_at),
    ends_at: toLocalInput(row.ends_at)
  }
}

const cancelEdit = () => {
  editingId.value = null
  editDraft.value = emptyBroadcast()
}

const saveBroadcast = async (row) => {
  savingBroadcast.value = true
  try {
    await apiClient.patch(`/admin/broadcasts/${row.id}`, {
      body: editDraft.value.body,
      url: row.kind === 'link' ? editDraft.value.url : null,
      committee_name: editDraft.value.committee_name,
      starts_at: toUtcIso(editDraft.value.starts_at),
      ends_at: toUtcIso(editDraft.value.ends_at)
    })
    cancelEdit()
    toastStore.showToast('Saved.', 'success')
    await loadBroadcasts()
  } catch (error) {
    // Backend errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

const moveBroadcast = async (row, delta) => {
  const group = groupOf(row)
  const index = group.findIndex((other) => other.id === row.id)
  const swapWith = index + delta
  if (swapWith < 0 || swapWith >= group.length) return

  ;[group[index], group[swapWith]] = [group[swapWith], group[index]]

  savingBroadcast.value = true
  try {
    // Renumber the whole group so equal positions cannot leave the order ambiguous.
    await Promise.all(
      group.map((entry, position) =>
        apiClient.patch(`/admin/broadcasts/${entry.id}`, { position })
      )
    )
    await loadBroadcasts()
  } catch (error) {
    // Backend errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

const deleteBroadcast = async (row) => {
  if (!window.confirm(`Delete "${row.body}"? This cannot be undone.`)) return

  savingBroadcast.value = true
  try {
    await apiClient.delete(`/admin/broadcasts/${row.id}`)
    toastStore.showToast('Deleted.', 'success')
    await loadBroadcasts()
  } catch (error) {
    // Backend errors pop up via the interceptor
  } finally {
    savingBroadcast.value = false
  }
}

// ---------- Conference checklist actions (shared labels) ----------
const loadChecklist = async () => {
  loadingChecklist.value = true
  try {
    const response = await apiClient.get('/admin/checklist')
    // Keep the ids: they are what the schools' ticks point at, so they must be sent back.
    checklistItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label
    }))
    checklistDirty.value = false
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingChecklist.value = false
  }
}

const addChecklistItem = () => {
  checklistItems.value.push({ id: null, label: '' }) // id null = a new line
  checklistDirty.value = true
}

const removeChecklistItem = (index) => {
  checklistItems.value.splice(index, 1)
  checklistDirty.value = true
}

const saveChecklist = async () => {
  if (checklistItems.value.some((item) => !item.label.trim())) {
    toastStore.showToast('Every checklist line needs a label.', 'error')
    return
  }

  savingChecklist.value = true
  try {
    const response = await apiClient.put('/admin/checklist', {
      items: checklistItems.value.map((item) => ({
        id: item.id,
        label: item.label.trim()
      }))
    })
    checklistItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label
    }))
    checklistDirty.value = false
    toastStore.showToast('Checklist saved.', 'success')

    // Line ids may have been added or removed, so re-read the progress view rather than
    // keep ticking against a stale list.
    if (progressSchoolId.value !== null) {
      await loadProgress()
    }
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    savingChecklist.value = false
  }
}

// ---------- Existing Schools: per-school detail, editing, deletion ----------
const selectedSchoolId = ref(null)
const schoolDetail = ref(null)
const schoolDraft = ref(null)
const delegateDrafts = ref([])
const savingSchool = ref(false)
const savingDelegateId = ref(null)
const reissuingId = ref(null)
const deletingSchool = ref(false)

const applySchoolDetail = (detail) => {
  schoolDetail.value = detail
  schoolDraft.value = { ...detail.school }
  delegateDrafts.value = (detail.delegates || []).map((row) => ({ ...row }))
}

const loadSchoolDetail = async () => {
  if (selectedSchoolId.value === null) {
    schoolDetail.value = null
    schoolDraft.value = null
    delegateDrafts.value = []
    return
  }
  try {
    const response = await apiClient.get(`/admin/schools/${selectedSchoolId.value}`)
    applySchoolDetail(response.data)
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  }
}

const schoolDirty = computed(() => {
  if (!schoolDetail.value || !schoolDraft.value) return false
  return Object.keys(schoolDraft.value).some(
    (key) =>
      String(schoolDraft.value[key] ?? '') !== String(schoolDetail.value.school[key] ?? '')
  )
})

const delegateDirty = (row) => {
  const original = schoolDetail.value?.delegates.find((d) => d.account_id === row.account_id)
  if (!original) return false
  return (
    row.country.trim() !== original.country || row.committee.trim() !== original.committee
  )
}

const saveSchool = async () => {
  if (!schoolDetail.value || !schoolDraft.value) return
  const changes = {}
  for (const key of Object.keys(schoolDraft.value)) {
    if (String(schoolDraft.value[key] ?? '') !== String(schoolDetail.value.school[key] ?? '')) {
      changes[key] = schoolDraft.value[key]
    }
  }

  savingSchool.value = true
  try {
    const response = await apiClient.patch(`/admin/schools/${schoolDetail.value.id}`, changes)
    // A rename rewrites the delegate labels server-side, so refresh from the response -
    // but keep whatever the admin has typed into the editable columns.
    const typed = new Map(delegateDrafts.value.map((row) => [row.account_id, row]))
    applySchoolDetail(response.data)
    delegateDrafts.value = delegateDrafts.value.map((fresh) => {
      const row = typed.get(fresh.account_id)
      return row ? { ...fresh, country: row.country, committee: row.committee } : fresh
    })
    await loadSchools()
    toastStore.showToast('School updated.', 'success')
  } catch (error) {
    // 409 / 400 / 422 all arrive as {"message": ...} and are toasted by the interceptor
  } finally {
    savingSchool.value = false
  }
}

const saveDelegate = async (row) => {
  if (!schoolDetail.value) return false
  const original = schoolDetail.value.delegates.find((d) => d.account_id === row.account_id)
  if (!original) return false

  const changes = {}
  if (row.country.trim() !== original.country) changes.country = row.country.trim()
  if (row.committee.trim() !== original.committee) changes.committee = row.committee.trim()
  if (!Object.keys(changes).length) return true

  savingDelegateId.value = row.account_id
  try {
    const response = await apiClient.patch(
      `/admin/schools/${schoolDetail.value.id}/delegates/${row.account_id}`,
      changes
    )
    Object.assign(row, response.data)
    const index = schoolDetail.value.delegates.findIndex(
      (d) => d.account_id === row.account_id
    )
    if (index !== -1) schoolDetail.value.delegates[index] = { ...response.data }
    toastStore.showToast('Delegate updated.', 'success')
    return true
  } catch (error) {
    return false
  } finally {
    savingDelegateId.value = null
  }
}

const reissueHash = async (row) => {
  // The regenerate endpoint identifies a delegate by committee + country, so pending edits
  // have to be saved first or it would reissue the hash of the old assignment.
  if (delegateDirty(row) && !(await saveDelegate(row))) return
  if (
    !window.confirm(
      `Reissue the hash for ${row.country} (${row.committee})?\n\nThe current hash stops working immediately.`
    )
  ) {
    return
  }

  reissuingId.value = row.account_id
  try {
    const response = await apiClient.post('/admin/hashes/regenerate/delegate', {
      committee: row.committee,
      country: row.country
    })
    row.hash = response.data.hash
    const original = schoolDetail.value.delegates.find((d) => d.account_id === row.account_id)
    if (original) original.hash = response.data.hash
    toastStore.showToast('Hash reissued.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    reissuingId.value = null
  }
}

const deleteSchool = async () => {
  const detail = schoolDetail.value
  if (!detail) return

  const delegates = detail.delegates.length
  const papers = detail.delegates.filter((row) => row.has_paper).length
  const warning =
    `Delete "${detail.school.school_name}"?\n\n` +
    `This removes ${delegates} delegate(s) and their hashes` +
    (papers ? `, plus ${papers} stored paper(s)` : '') +
    '.\n\nThis cannot be undone.'
  if (!window.confirm(warning)) return

  deletingSchool.value = true
  try {
    const response = await apiClient.delete(`/admin/schools/${detail.id}`, {
      // The server checks this, so a stray request cannot delete a school by id alone.
      params: { confirm: detail.school.school_name }
    })
    toastStore.showToast(
      `${response.data.school} deleted (${response.data.delegates_deleted} delegate(s)).`,
      'success'
    )
    selectedSchoolId.value = null
    schoolDetail.value = null
    schoolDraft.value = null
    delegateDrafts.value = []
    await loadSchools()
  } catch (error) {
    // toasted by the interceptor
  } finally {
    deletingSchool.value = false
  }
}

// ---------- Checklist progress actions (per school) ----------
const loadSchools = async () => {
  try {
    const response = await apiClient.get('/admin/schools')
    schools.value = response.data.schools || []
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  }
}

const loadProgress = async () => {
  if (progressSchoolId.value === null) {
    progressItems.value = []
    savedProgressSchoolId.value = null
    progressDirty.value = false
    return
  }

  loadingProgress.value = true
  try {
    const response = await apiClient.get(`/admin/schools/${progressSchoolId.value}/checklist`)
    progressItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label,
      completed: item.completed
    }))
    savedProgressSchoolId.value = progressSchoolId.value
    progressDirty.value = false
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingProgress.value = false
  }
}

// Switching schools throws the tick draft away, so ask first and put the picker back.
const onProgressSchoolChange = async () => {
  if (progressDirty.value && !window.confirm('Discard the unsaved progress changes?')) {
    progressSchoolId.value = savedProgressSchoolId.value
    return
  }
  await loadProgress()
}

const saveProgress = async () => {
  if (progressSchoolId.value === null) return

  savingProgress.value = true
  try {
    const response = await apiClient.patch(`/admin/schools/${progressSchoolId.value}/checklist`, {
      items: progressItems.value.map((item) => ({
        id: item.id,
        completed: item.completed
      }))
    })
    progressItems.value = (response.data.items || []).map((item) => ({
      id: item.id,
      label: item.label,
      completed: item.completed
    }))
    progressDirty.value = false
    toastStore.showToast('Progress saved.', 'success')
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    savingProgress.value = false
  }
}

// ---------- Timeline actions ----------
const loadTimeline = async () => {
  loadingTimeline.value = true
  try {
    const response = await apiClient.get('/admin/timeline')
    // Stored as naive UTC, edited as local wall-clock time.
    timelineEvents.value = (response.data.events || []).map((event) => ({
      id: event.id,
      phase: event.phase,
      label: event.label,
      starts_at: toLocalInput(event.starts_at)
    }))
    timelineDirty.value = false
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    loadingTimeline.value = false
  }
}

const addTimelineEvent = () => {
  timelineEvents.value.push({
    id: null,
    phase: 'preConference',
    label: '',
    starts_at: ''
  })
  timelineDirty.value = true
}

const removeTimelineEvent = (index) => {
  timelineEvents.value.splice(index, 1)
  timelineDirty.value = true
}

const saveTimeline = async () => {
  if (timelineEvents.value.some((event) => !event.label.trim())) {
    toastStore.showToast('Every timeline event needs a label.', 'error')
    return
  }
  if (timelineEvents.value.some((event) => !event.starts_at)) {
    toastStore.showToast('Every timeline event needs a date and time.', 'error')
    return
  }

  savingTimeline.value = true
  try {
    const response = await apiClient.put('/admin/timeline', {
      events: timelineEvents.value.map((event) => ({
        phase: event.phase,
        label: event.label.trim(),
        starts_at: toUtcIso(event.starts_at)
      }))
    })
    // The server returns them sorted by time, which is the order the editor shows.
    timelineEvents.value = (response.data.events || []).map((event) => ({
      id: event.id,
      phase: event.phase,
      label: event.label,
      starts_at: toLocalInput(event.starts_at)
    }))
    timelineDirty.value = false
    toastStore.showToast('Timeline saved.', 'success')
  } catch (error) {
    // Backend errors pop up via the global toast interceptor
  } finally {
    savingTimeline.value = false
  }
}

// ---------- Committees: create, rename, chairs, delegate removal ----------
// Also feeds the <datalist> every committee input in the page uses, because a delegate can
// only be minted into a committee that exists.
const committeeNames = ref([])
const selectedCommittee = ref('')
const committeeDetail = ref(null)
const committeeDraft = ref(null)
const chairDrafts = ref([])
const newCommittee = ref({ committee_name: '', committee_type: '', topic: '' })
const creatingCommittee = ref(false)
const savingCommittee = ref(false)
const newChair = ref({ name: '', email: '' })
const addingChair = ref(false)
const savingChairId = ref(null)
const reissuingChairId = ref(null)
const removingChairId = ref(null)
const reissuingDelegateId = ref(null)
const removingDelegateId = ref(null)

const loadCommittees = async () => {
  try {
    const response = await apiClient.get('/admin/committees')
    committeeNames.value = response.data || []
  } catch (error) {
    // toasted by the interceptor
  }
}

const applyCommitteeDetail = (detail) => {
  committeeDetail.value = detail
  committeeDraft.value = {
    committee_name: detail.committee_name,
    committee_type: detail.committee_type || '',
    topic: detail.topic || ''
  }
  chairDrafts.value = (detail.chairs || []).map((chair) => ({ ...chair }))
}

const loadCommitteeDetail = async () => {
  if (!selectedCommittee.value) {
    committeeDetail.value = null
    committeeDraft.value = null
    chairDrafts.value = []
    return
  }
  try {
    const response = await apiClient.get(
      `/admin/committees/${encodeURIComponent(selectedCommittee.value)}`
    )
    applyCommitteeDetail(response.data)
  } catch (error) {
    // toasted by the interceptor
  }
}

const createCommittee = async () => {
  const name = newCommittee.value.committee_name.trim()
  if (!name) {
    toastStore.showToast('Enter a committee name.', 'error')
    return
  }

  creatingCommittee.value = true
  try {
    const response = await apiClient.post('/admin/committees', {
      committee_name: name,
      committee_type: newCommittee.value.committee_type.trim() || null,
      topic: newCommittee.value.topic.trim() || null
    })
    newCommittee.value = { committee_name: '', committee_type: '', topic: '' }
    await loadCommittees()
    selectedCommittee.value = response.data.committee_name
    applyCommitteeDetail(response.data)
    toastStore.showToast('Committee created.', 'success')
  } catch (error) {
    // 409 / 400 / 422 arrive with a message and are toasted by the interceptor
  } finally {
    creatingCommittee.value = false
  }
}

const committeeDirty = computed(() => {
  if (!committeeDetail.value || !committeeDraft.value) return false
  return (
    committeeDraft.value.committee_name.trim() !== committeeDetail.value.committee_name ||
    (committeeDraft.value.committee_type || '') !== (committeeDetail.value.committee_type || '') ||
    (committeeDraft.value.topic || '') !== (committeeDetail.value.topic || '')
  )
})

const saveCommittee = async () => {
  if (!committeeDetail.value || !committeeDraft.value) return
  const changes = {}
  if (committeeDraft.value.committee_name.trim() !== committeeDetail.value.committee_name) {
    changes.committee_name = committeeDraft.value.committee_name.trim()
  }
  if ((committeeDraft.value.committee_type || '') !== (committeeDetail.value.committee_type || '')) {
    changes.committee_type = committeeDraft.value.committee_type.trim() || null
  }
  if ((committeeDraft.value.topic || '') !== (committeeDetail.value.topic || '')) {
    changes.topic = committeeDraft.value.topic.trim() || null
  }

  savingCommittee.value = true
  try {
    const response = await apiClient.patch(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}`,
      changes
    )
    // Keep unsaved chair edits; a rename does not touch them.
    const typed = new Map(chairDrafts.value.map((chair) => [chair.account_id, chair]))
    applyCommitteeDetail(response.data)
    chairDrafts.value = chairDrafts.value.map((fresh) => {
      const row = typed.get(fresh.account_id)
      return row ? { ...fresh, name: row.name, email: row.email } : fresh
    })
    selectedCommittee.value = response.data.committee_name
    await loadCommittees()
    toastStore.showToast('Committee updated.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    savingCommittee.value = false
  }
}

const chairDirty = (row) => {
  const original = committeeDetail.value?.chairs.find((c) => c.account_id === row.account_id)
  if (!original) return false
  return row.name.trim() !== original.name || row.email.trim() !== original.email
}

const saveChair = async (row) => {
  if (!committeeDetail.value) return false
  const original = committeeDetail.value.chairs.find((c) => c.account_id === row.account_id)
  if (!original) return false
  const changes = {}
  if (row.name.trim() !== original.name) changes.name = row.name.trim()
  if (row.email.trim() !== original.email) changes.email = row.email.trim()
  if (!Object.keys(changes).length) return true

  savingChairId.value = row.account_id
  try {
    const response = await apiClient.patch(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/chairs/${row.account_id}`,
      changes
    )
    Object.assign(row, response.data)
    const index = committeeDetail.value.chairs.findIndex((c) => c.account_id === row.account_id)
    if (index !== -1) committeeDetail.value.chairs[index] = { ...response.data }
    toastStore.showToast('Chair updated.', 'success')
    return true
  } catch (error) {
    return false
  } finally {
    savingChairId.value = null
  }
}

const addChair = async () => {
  if (!committeeDetail.value) return
  const name = newChair.value.name.trim()
  const email = newChair.value.email.trim()
  if (!name || !email) {
    toastStore.showToast('Enter the chair name and email.', 'error')
    return
  }

  addingChair.value = true
  try {
    const response = await apiClient.post(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/chairs`,
      { name, email }
    )
    committeeDetail.value.chairs = [...committeeDetail.value.chairs, response.data]
    chairDrafts.value = [...chairDrafts.value, { ...response.data }]
    newChair.value = { name: '', email: '' }
    toastStore.showToast('Chair added — hand them the hash.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    addingChair.value = false
  }
}

const reissueChair = async (row) => {
  if (chairDirty(row) && !(await saveChair(row))) return
  if (!window.confirm(`Reissue ${row.name}'s hash?\n\nThe current hash stops working immediately.`)) {
    return
  }

  reissuingChairId.value = row.account_id
  try {
    const response = await apiClient.post('/admin/hashes/regenerate/chair', {
      account_id: row.account_id
    })
    row.hash = response.data.hash
    const index = committeeDetail.value.chairs.findIndex((c) => c.account_id === row.account_id)
    if (index !== -1) committeeDetail.value.chairs[index].hash = response.data.hash
    toastStore.showToast('Hash reissued.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    reissuingChairId.value = null
  }
}

const removeChair = async (row) => {
  if (
    !window.confirm(
      `Remove ${row.name} as a chair of ${committeeDetail.value.committee_name}?\n\nTheir account and hash are deleted.`
    )
  ) {
    return
  }

  removingChairId.value = row.account_id
  try {
    await apiClient.delete(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/chairs/${row.account_id}`
    )
    committeeDetail.value.chairs = committeeDetail.value.chairs.filter(
      (c) => c.account_id !== row.account_id
    )
    chairDrafts.value = chairDrafts.value.filter((c) => c.account_id !== row.account_id)
    toastStore.showToast('Chair removed.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    removingChairId.value = null
  }
}

const reissueCommitteeDelegate = async (row) => {
  if (
    !window.confirm(
      `Reissue the hash for ${row.country} (${row.school_name})?\n\nThe current hash stops working immediately.`
    )
  ) {
    return
  }

  reissuingDelegateId.value = row.account_id
  try {
    const response = await apiClient.post('/admin/hashes/regenerate/delegate', {
      committee: committeeDetail.value.committee_name,
      country: row.country
    })
    row.hash = response.data.hash
    toastStore.showToast('Hash reissued.', 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    reissuingDelegateId.value = null
  }
}

const removeCommitteeDelegate = async (row) => {
  const graded = row.paper_status === 'graded' ? '\n\nThis delegate has a graded paper.' : ''
  if (
    !window.confirm(
      `Remove ${row.country} (${row.school_name}) from ${committeeDetail.value.committee_name}?` +
        '\n\nTheir account, hash and stored paper are deleted.' +
        graded
    )
  ) {
    return
  }

  removingDelegateId.value = row.account_id
  try {
    const response = await apiClient.delete(
      `/admin/committees/${encodeURIComponent(committeeDetail.value.committee_name)}/delegates/${row.account_id}`
    )
    committeeDetail.value.delegates = committeeDetail.value.delegates.filter(
      (d) => d.account_id !== row.account_id
    )
    toastStore.showToast(`${response.data.delegate} removed from the committee.`, 'success')
  } catch (error) {
    // toasted by the interceptor
  } finally {
    removingDelegateId.value = null
  }
}

// ---------- Initial load ----------
onMounted(async () => {
  try {
    const response = await apiClient.get('/admin/dashboard-stats')

    totalDelegates.value = response.data.totalDelegates
    committeeCounts.value = response.data.committeeCounts
    storage.value = response.data.storage
    downtimeEvents.value = response.data.downtimeEvents

    await fetchPortHealth()
    await loadCommittees()
  } catch (error) {
    // Backend errors will automatically pop up via your global toast store!
  }
})
</script>

<style scoped>
.admin-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  color: #00007e93;
  font-family: Arial, sans-serif;
}

.page-header h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #00007e;
}

/* VIEW TOGGLE */
.toggle-container {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.toggle-btn {
  background-color: #f5fafd;
  color: #5b6b7d;
  border: 1px solid #e8c604;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: bold;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-btn:hover {
  color: #00007e;
  border-color: #009ddb;
}

.toggle-btn.active {
  background-color: #009ddbda;
  border-color: #009ddb;
  color: #00007e;
}

/* SECTION CARDS */
.section-card {
  background-color: #ffffff;
  border: 1px solid #e8c604;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.section-card h2 {
  margin: 0;
  font-size: 1.1rem;
  color: #00007e;
}

.section-card h3 {
  margin: 0;
  font-size: 0.95rem;
  color: #00007e;
}

.section-desc {
  margin: 0;
  font-size: 0.85rem;
  color: #5b6b7d;
}

.card-header-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* BUTTONS & EXPORTS */
.action-buttons-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.btn-action {
  background-color: #f5fafd;
  color: #00007e;
  border: 1px solid #e8c604;
  padding: 12px;
  border-radius: 6px;
  font-weight: bold;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-action:hover {
  background-color: #e8c604;
}

.btn-export {
  border-color: #16a34a;
  color: #166534;
}

.btn-export:hover {
  background-color: #dcfce7;
}

.btn-refresh {
  background-color: #009ddbda;
  color: #00007e;
  border: none;
  padding: 8px 14px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: #f5fafd;
  color: #00007e;
  border: 1px solid #e8c604;
  padding: 8px 14px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-secondary:hover {
  background-color: #e8c604;
}

.btn-danger {
  background-color: #fee2e2;
  color: #991b1b;
  border: 1px solid #ef4444;
  padding: 8px 14px;
  border-radius: 4px;
  font-weight: bold;
  cursor: pointer;
}

.btn-danger:hover {
  background-color: #dc2626;
  color: #ffffff;
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  background-color: #f5fafd;
  color: #ef4444;
  border: 1px solid #e8c604;
  border-radius: 4px;
  width: 34px;
  cursor: pointer;
}

.btn-icon:hover {
  border-color: #ef4444;
}

.btn-copy {
  background-color: #f5fafd;
  color: #00007e;
  border: 1px solid #e8c604;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 0.75rem;
  font-weight: bold;
  cursor: pointer;
}

.btn-copy:hover {
  border-color: #009ddb;
}

/* METRICS GRID */
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.total-badge {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #f5fafd;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 1rem;
}

.total-badge strong {
  color: #00007e;
  font-size: 1.3rem;
}

.committee-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.committee-item {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  padding: 6px 10px;
  background-color: #f5fafd;
  border-radius: 4px;
}

.committee-name {
  color: #5b6b7d;
}

.committee-count {
  font-weight: bold;
}

/* STORAGE BAR */
.storage-info {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.storage-values {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
}

.progress-bar-bg {
  background-color: #f5fafd;
  height: 16px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e8c604;
}

.progress-bar-fill {
  height: 100%;
  background-color: #16a34a;
  transition: width 0.4s ease;
}

.progress-bar-fill.warning {
  background-color: #e8c604;
}

.percentage-label {
  font-size: 0.8rem;
  color: #5b6b7d;
  text-align: right;
}

/* PORTS GRID */
.ports-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.port-card {
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 6px;
  padding: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.port-card.unreachable {
  border-color: #ef4444;
}

.port-info {
  display: flex;
  flex-direction: column;
}

.port-name {
  font-weight: bold;
  font-size: 0.9rem;
}

.port-number {
  font-size: 0.75rem;
  color: #6b7c8d;
}

.status-badge {
  font-size: 0.8rem;
  font-weight: bold;
  padding: 4px 8px;
  border-radius: 4px;
}

.status-badge.healthy {
  color: #166534;
  background-color: #dcfce7;
}

.status-badge.unreachable {
  color: #991b1b;
  background-color: #fee2e2;
}

/* DOWNTIME TIMELINE */
.no-downtime {
  background-color: #dcfce7;
  color: #166534;
  padding: 12px;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: bold;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.timeline-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  background-color: #f5fafd;
  padding: 12px;
  border-radius: 6px;
  border-left: 4px solid #ef4444;
}

.timeline-dot {
  width: 10px;
  height: 10px;
  background-color: #ef4444;
  color: #ffffff;
  border-radius: 50%;
  margin-top: 4px;
}

.timeline-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.85rem;
}

.timeline-details {
  display: flex;
  gap: 10px;
  align-items: center;
}

.duration-badge {
  background-color: #fee2e2;
  color: #991b1b;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: bold;
}

.reason-text {
  color: #5b6b7d;
}

/* FORMS */
.field-label {
  font-size: 0.8rem;
  color: #5b6b7d;
  margin-bottom: -8px;
}

.text-input {
  width: 100%;
  box-sizing: border-box;
  background-color: #ffffff;
  border: 1px solid #e8c604;
  border-radius: 4px;
  padding: 9px 12px;
  color: #00007e93;
  font-size: 0.85rem;
  font-family: inherit;
}

.text-input:focus {
  outline: none;
  border-color: #009ddb;
}

.form-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 8px;
  align-items: center;
}

.row-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

/* HASH RESULTS */
.hash-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 6px;
  padding: 12px;
}

.school-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0 16px;
}

.field-pair {
  display: flex;
  flex-direction: column;
}

.school-list {
  margin-top: 18px;
}

.school-block {
  margin-bottom: 12px;
}

.delegate-table {
  margin-top: 12px;
}

.delegate-head,
.delegate-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr 1.2fr 1.3fr auto;
  gap: 10px;
  align-items: center;
}

.delegate-head {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #00007e93;
  padding-bottom: 6px;
  border-bottom: 1px solid #e6e6f0;
}

.delegate-row {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f6;
}

.delegate-label {
  font-weight: 600;
}

.delegate-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.chair-table {
  margin-bottom: 14px;
}

.chair-head,
.chair-row {
  display: grid;
  grid-template-columns: 1.1fr 1.3fr 1.3fr auto;
  gap: 10px;
  align-items: center;
}

.chair-head {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #00007e93;
  padding-bottom: 6px;
  border-bottom: 1px solid #e6e6f0;
}

.chair-row {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f6;
}

.chair-add {
  margin-top: 6px;
}

/* The committees view shows one fewer editable column than the schools view. */
.committee-row {
  grid-template-columns: 1.2fr 0.8fr 1.1fr 1.2fr auto;
}

.btn-copy-danger {
  color: #b3261e;
  border-color: #e6b4b0;
}

.paper-badge {
  font-size: 0.8rem;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef0f7;
  white-space: nowrap;
}

.paper-badge.is-submitted {
  background: #e8f1ff;
}

.paper-badge.is-graded {
  background: #e6f7ec;
}

.btn-danger {
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  background: #b3261e;
  color: #ffffff;
  font-weight: bold;
  cursor: pointer;
}

.btn-danger:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.school-list h3 {
  margin: 0 0 8px;
}

.hash-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.85rem;
}

.hash-name {
  flex: 1;
  color: #00007e93;
}

.hash-value {
  font-family: 'Courier New', monospace;
  color: #00007e;
  background-color: #f5fafd;
  padding: 3px 8px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}

.empty-state {
  font-size: 0.85rem;
  color: #6b7c8d;
  padding: 8px 0;
}

/* AWARDS OVERVIEW */
.committee-awards-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.awards-card {
  background-color: #f5fafd;
  border: 1px solid #e8c604;
  border-radius: 6px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.award-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  padding: 6px 10px;
  background-color: #ffffff;
  border-radius: 4px;
}

.award-country {
  color: #00007e93;
}

.award-name {
  color: #00007e;
  font-weight: bold;
}

/* ANNOUNCEMENTS & CONFERENCE LINKS */
.broadcast-form {
  display: flex;
  flex-direction: column;
}

.schedule-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.capacity-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 4px;
}

.capacity-chip {
  border: 1px solid #e8c604;
  border-radius: 10px;
  padding: 2px 8px;
  font-size: 0.8rem;
  color: #00007e;
  background-color: #fffdf2;
}

.capacity-chip.full {
  border-color: #b33;
  color: #b33;
  background-color: #fdecec;
}

.capacity-note {
  color: #666;
  font-size: 0.8rem;
}

.capacity-warning {
  color: #b33;
  font-size: 0.8rem;
}

.broadcast-group {
  margin-top: 14px;
}

.broadcast-group h3 {
  color: #00007e;
  font-size: 0.95rem;
  margin: 0 0 8px;
}

.broadcast-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  border: 1px solid #e8c604;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  background-color: #ffffff;
}

.broadcast-row.editing {
  flex-direction: column;
  align-items: stretch;
}

.broadcast-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-width: 240px;
}

.broadcast-body {
  color: #00007e;
  font-weight: bold;
}

.broadcast-url {
  color: #009ddb;
  font-size: 0.85rem;
  word-break: break-all;
}

.broadcast-schedule {
  color: #666;
  font-size: 0.8rem;
}

.broadcast-state {
  font-size: 0.75rem;
  font-weight: bold;
  padding: 3px 8px;
  border-radius: 10px;
  background-color: #eef6fb;
  color: #00007e;
}

.broadcast-state.scheduled {
  background-color: #fff7dd;
  color: #8a6d00;
}

.broadcast-state.ended {
  background-color: #fdecec;
  color: #b33;
}

.broadcast-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-icon:disabled,
.btn-refresh:disabled,
.btn-danger:disabled {
  opacity: 0.45;
  cursor: default;
}

/* CONFERENCE CHECKLIST */
.checklist-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.checklist-row .text-input {
  flex: 1;
}

.progress-label {
  flex: 1;
  color: #00007e;
}

/* TIMELINE EDITOR */
.timeline-editor-row {
  display: grid;
  grid-template-columns: 180px 1fr 220px auto;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}

.checklist-row input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: #009ddb;
  cursor: pointer;
}

@media (max-width: 900px) {
  .action-buttons-grid,
  .metrics-grid,
  .ports-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .schedule-row {
    grid-template-columns: 1fr;
  }

  .timeline-editor-row {
    grid-template-columns: 1fr;
  }

  .row-actions {
    justify-content: flex-start;
  }
}
</style>
