<script>
  import { updatePointBoundaries } from '$lib/api';

  export let gameId = '';
  export let points = [];
  export let onsaved = async () => {};

  let draftPoints = [];
  let saving = false;
  let error = '';
  let success = '';

  $: draftPoints = points.map((point) => ({
    point_id: point.point_id,
    point_ordinal: point.point_ordinal,
    start_video_ts_ms: point.start_video_ts_ms,
    end_video_ts_ms: point.end_video_ts_ms
  }));

  function addPoint() {
    const lastPoint = draftPoints[draftPoints.length - 1];
    const start = lastPoint ? Number(lastPoint.end_video_ts_ms) + 1 : 0;
    draftPoints = [
      ...draftPoints,
      {
        point_id: '',
        point_ordinal: draftPoints.length + 1,
        start_video_ts_ms: start,
        end_video_ts_ms: start + 12000
      }
    ];
  }

  function removePoint(index) {
    draftPoints = draftPoints.filter((_, currentIndex) => currentIndex !== index);
  }

  async function savePoints() {
    saving = true;
    error = '';
    success = '';

    try {
      const result = await updatePointBoundaries(gameId, {
        points: draftPoints.map((point) => ({
          start_video_ts_ms: Number(point.start_video_ts_ms),
          end_video_ts_ms: Number(point.end_video_ts_ms)
        }))
      });
      success = `Saved ${result.points.length} points. Rebucketing touched ${result.events_rebucketed} events and ${result.observations_rebucketed} observations.`;
      await onsaved(result);
    } catch (caught) {
      error = caught.message;
    } finally {
      saving = false;
    }
  }
</script>

<section class="panel pad stack">
  <div class="row" style="justify-content: space-between;">
    <div>
      <div class="eyebrow">Point Boundaries</div>
      <h3>Rebucket before timeline review</h3>
    </div>
    <div class="actions">
      <button class="btn secondary" type="button" on:click={addPoint}>Add point</button>
      <button class="btn primary" type="button" on:click={savePoints} disabled={saving || draftPoints.length === 0}>
        {saving ? 'Saving...' : 'Save boundaries'}
      </button>
    </div>
  </div>

  <p class="subtle">
    This editor writes the full boundary set back to the backend. If corrections already exist, the
    backend will reject the save to keep memory provenance honest.
  </p>

  <div class="editor-grid">
    {#each draftPoints as point, index}
      <div class="editor-row">
        <div class="field">
          <label for={`point-label-${index}`}>Point</label>
          <input id={`point-label-${index}`} value={`#${index + 1}`} readonly />
        </div>
        <div class="field">
          <label for={`point-start-${index}`}>Start (ms)</label>
          <input id={`point-start-${index}`} type="number" bind:value={point.start_video_ts_ms} min="0" />
        </div>
        <div class="field">
          <label for={`point-end-${index}`}>End (ms)</label>
          <input id={`point-end-${index}`} type="number" bind:value={point.end_video_ts_ms} min="0" />
        </div>
        <button class="btn ghost" type="button" on:click={() => removePoint(index)} disabled={draftPoints.length === 1}>
          Remove
        </button>
      </div>
    {/each}
  </div>

  {#if error}
    <div class="error">{error}</div>
  {/if}

  {#if success}
    <div class="success">{success}</div>
  {/if}
</section>
