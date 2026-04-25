<script>
  import { submitCorrection } from '$lib/api';

  export let gameId = '';
  export let points = [];
  export let events = [];
  export let onsubmitted = async () => {};

  let coachId = 'coach_alpha';
  let correctionType = 'reclassify';
  let pointId = '';
  let sourceEventId = '';
  let proposedType = 'completion';
  let proposedTeam = 'dark';
  let note = '';
  let open = false;
  let submitting = false;
  let error = '';
  let success = '';

  $: pointOptions = points;
  $: if (pointOptions.length > 0 && !pointOptions.some((point) => point.point_id === pointId)) {
    pointId = pointOptions[0].point_id;
  }
  $: selectedPoint = pointOptions.find((point) => point.point_id === pointId) || null;
  $: pointEvents = events.filter((event) => event.point_id === pointId);
  $: if (pointEvents.length > 0 && !pointEvents.some((event) => event.event_id === sourceEventId)) {
    sourceEventId = pointEvents[0].event_id;
  }
  $: requiresSource = ['flag_wrong', 'reclassify', 'delete_spurious'].includes(correctionType);
  $: requiresProposed = ['reclassify', 'mark_missed'].includes(correctionType);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!selectedPoint) {
      error = 'Pick a point before submitting a correction.';
      return;
    }

    submitting = true;
    error = '';
    success = '';

    const payload = {
      point_id: selectedPoint.point_id,
      point_ordinal: selectedPoint.point_ordinal,
      coach_id: coachId,
      correction_type: correctionType,
      note
    };

    if (requiresSource) {
      payload.source_event_id = sourceEventId;
    }
    if (requiresProposed) {
      payload.proposed_event = {
        type: proposedType,
        team: proposedTeam
      };
    }

    try {
      const result = await submitCorrection(gameId, payload);
      success = `Correction saved. Created memory: ${result.created_memory_ids.join(', ') || 'none'}.`;
      note = '';
      await onsubmitted(result);
    } catch (caught) {
      error = caught.message;
    } finally {
      submitting = false;
    }
  }
</script>

<section class="panel pad drawer">
  <div class="row" style="justify-content: space-between;">
    <div>
      <div class="eyebrow">Coach Corrections</div>
      <h3>Teach the memory loop</h3>
    </div>
    <button class="btn secondary" type="button" on:click={() => (open = !open)}>
      {open ? 'Hide editor' : 'Open editor'}
    </button>
  </div>

  <p class="subtle">
    Submit the four v1 correction types directly against the stored timeline. Boundary edits should be
    saved first.
  </p>

  {#if open}
    <form class="stack" on:submit={handleSubmit}>
      <div class="grid two">
        <div class="field">
          <label for="coach-id">Coach ID</label>
          <input id="coach-id" bind:value={coachId} placeholder="coach_alpha" required />
        </div>
        <div class="field">
          <label for="correction-type">Correction type</label>
          <select id="correction-type" bind:value={correctionType}>
            <option value="reclassify">Reclassify type</option>
            <option value="mark_missed">Mark missed</option>
            <option value="flag_wrong">Flag wrong</option>
            <option value="delete_spurious">Delete spurious</option>
          </select>
        </div>
      </div>

      <div class="grid two">
        <div class="field">
          <label for="point-id">Point</label>
          <select id="point-id" bind:value={pointId} disabled={pointOptions.length === 0}>
            {#each pointOptions as point}
              <option value={point.point_id}>
                Point {point.point_ordinal} · {point.start_video_ts_ms}–{point.end_video_ts_ms} ms
              </option>
            {/each}
          </select>
        </div>

        {#if requiresSource}
          <div class="field">
            <label for="source-event">Source event</label>
            <select id="source-event" bind:value={sourceEventId} disabled={pointEvents.length === 0}>
              {#each pointEvents as timelineEvent}
                <option value={timelineEvent.event_id}>
                  {timelineEvent.type} · {timelineEvent.team} · {timelineEvent.video_ts_ms} ms
                </option>
              {/each}
            </select>
          </div>
        {/if}
      </div>

      {#if requiresProposed}
        <div class="grid two">
          <div class="field">
            <label for="proposed-type">Proposed event type</label>
            <select id="proposed-type" bind:value={proposedType}>
              <option value="completion">completion</option>
              <option value="turnover">turnover</option>
              <option value="goal">goal</option>
              <option value="possession_start">possession_start</option>
              <option value="possession_end">possession_end</option>
              <option value="point_end">point_end</option>
              <option value="unknown">unknown</option>
            </select>
          </div>
          <div class="field">
            <label for="proposed-team">Proposed team</label>
            <select id="proposed-team" bind:value={proposedTeam}>
              <option value="dark">dark</option>
              <option value="light">light</option>
              <option value="unknown">unknown</option>
              <option value="none">none</option>
            </select>
          </div>
        </div>
      {/if}

      <div class="field">
        <label for="note">Coach note</label>
        <textarea id="note" bind:value={note} placeholder="Why should the model learn this correction?"></textarea>
      </div>

      {#if error}
        <div class="error">{error}</div>
      {/if}

      {#if success}
        <div class="success">{success}</div>
      {/if}

      <div class="actions">
        <button class="btn primary" type="submit" disabled={submitting || pointOptions.length === 0}>
          {submitting ? 'Saving...' : 'Submit correction'}
        </button>
        <button class="btn ghost" type="button" on:click={() => (open = false)}>Close</button>
      </div>
    </form>
  {/if}
</section>
