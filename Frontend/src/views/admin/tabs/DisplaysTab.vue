<template>
<!-- DELEGATES: the announcement bar and the links panel on the delegate dashboard. -->
<section class="displays-section">
  <header class="displays-section-head">
    <h2 class="displays-section-title">Delegates</h2>
    <p class="displays-section-desc">
      What every delegate sees on their dashboard: the announcement bar across the top, and
      the links in the "Conference &amp; General Info" panel. The form on the left publishes;
      the list on the right is what is already live.
    </p>
  </header>

  <div class="displays-grid">
    <BroadcastEditorCard />
    <BroadcastListCard />
  </div>
</section>

<!-- ADVISORS: the shared action checklist and each school's ticks against it. -->
<section class="displays-section">
  <header class="displays-section-head">
    <h2 class="displays-section-title">Advisors</h2>
    <p class="displays-section-desc">
      The conference action checklist on every advisor's dashboard. Its lines are shared by
      all schools (left); which of them a school has ticked is per school (right).
    </p>
  </header>

  <div class="displays-grid">
    <ChecklistLabelsCard />
    <ChecklistProgressCard />
  </div>
</section>

<!-- CHAIRS: the conference timeline. One card, so it keeps the full width. -->
<section class="displays-section">
  <header class="displays-section-head">
    <h2 class="displays-section-title">Chairs</h2>
    <p class="displays-section-desc">
      The conference schedule every chair sees on their committee overview, and the line the
      header countdown reads its start date from.
    </p>
  </header>

  <TimelineCard />
</section>
</template>

<script setup>
import BroadcastEditorCard from './displays/BroadcastEditorCard.vue'
import BroadcastListCard from './displays/BroadcastListCard.vue'
import ChecklistLabelsCard from './displays/ChecklistLabelsCard.vue'
import ChecklistProgressCard from './displays/ChecklistProgressCard.vue'
import TimelineCard from './displays/TimelineCard.vue'

// The "Delegate Content" and "Timeline" tabs were the same job from three directions: what
// one role sees on their own dashboard. Grouping them by role keeps the card behaviour and
// the endpoints exactly as they were - only the addressing changed - and puts the editor that
// publishes next to the list that shows what is live.
//
// Each card owns its own state and its own entry refresh, so this component is layout only:
// there is nothing here to keep in step when a card changes.
</script>
