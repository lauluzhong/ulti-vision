<script>
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import CorrectionDrawer from '$lib/components/CorrectionDrawer.svelte';
  import PointBoundaryEditor from '$lib/components/PointBoundaryEditor.svelte';
  import { fetchGameEvents, fetchGamePoints, fetchJobStatus, gameVideoUrl } from '$lib/api';
  import { formatTimestamp, groupEventsByPoint, summarizeGameStats } from '$lib/stats';

  let job = null;
  let events = [];
  let points = [];
  let loading = true;
  let error = '';
  let selectedTimestamp = null;
  let lastCorrection = null;
  let pollHandle = null;
  let videoElement = null;
  let videoError = '';
  const emptyCaptions = 'data:text/vtt;charset=utf-8,WEBVTT%0A%0A';

  $: gameId = $page.params.gameId;
  $: stats = summarizeGameStats(events);
  $: groupedEvents = groupEventsByPoint(events);
  $: pointsById = new Map(points.map((point) => [point.point_id, point]));
  $: videoSource = gameVideoUrl(gameId);
  $: if (videoElement && selectedTimestamp !== null) {
    const targetSeconds = selectedTimestamp / 1000;
    if (Math.abs(videoElement.currentTime - targetSeconds) > 0.3) {
      videoElement.currentTime = targetSeconds;
    }
  }

  async function loadSnapshot() {
    const [jobSnapshot, eventSnapshot, pointSnapshot] = await Promise.all([
      fetchJobStatus(gameId),
      fetchGameEvents(gameId),
      fetchGamePoints(gameId)
    ]);
    job = jobSnapshot;
    events = eventSnapshot.events;
    points = pointSnapshot.points;
    if (selectedTimestamp === null && events.length > 0) {
      selectedTimestamp = events[0].video_ts_ms;
    }
  }

  async function refreshAll() {
    loading = true;
    error = '';
    try {
      await loadSnapshot();
    } catch (caught) {
      error = caught.message;
    } finally {
      loading = false;
    }
  }

  function startPolling() {
    clearInterval(pollHandle);
    pollHandle = setInterval(async () => {
      try {
        await loadSnapshot();
        if (job?.status === 'complete' || job?.status === 'failed') {
          clearInterval(pollHandle);
          pollHandle = null;
        }
      } catch (caught) {
        error = caught.message;
      }
    }, 3000);
  }

  onMount(async () => {
    await refreshAll();
    if (!job || (job.status !== 'complete' && job.status !== 'failed')) {
      startPolling();
    }
  });

  onDestroy(() => {
    clearInterval(pollHandle);
  });

  function selectTimestamp(ms) {
    selectedTimestamp = ms;
  }

  async function handleBoundarySaved() {
    await refreshAll();
  }

  async function handleCorrectionSubmitted(result) {
    lastCorrection = result;
  }
</script>

<div class="shell">
  <section class="hero" style="margin-bottom: 1rem;">
    <span class="eyebrow">Game Room</span>
    <h1>{gameId}</h1>
    <div class="row">
      <span class={`status-pill ${job?.status || ''}`}>
        {job?.status || 'loading'}
      </span>
      <span class="tag">Stage: {job?.stage || 'pending'}</span>
      <span class="tag">
        Points: {job?.progress?.points_completed ?? 0}/{job?.progress?.points_total ?? 0}
      </span>
    </div>
  </section>

  {#if error}
    <div class="error" style="margin-bottom: 1rem;">{error}</div>
  {/if}

  <section class="grid three" style="margin-bottom: 1rem;">
    <div class="panel pad metric">
      <span class="label">Completion rate</span>
      <strong>{stats.completionRate}%</strong>
      <span>{stats.completions} completions over {stats.completions + stats.turnovers} tracked possessions</span>
    </div>
    <div class="panel pad metric">
      <span class="label">Goals</span>
      <strong>{stats.goals}</strong>
      <span>{groupedEvents.length} point buckets currently loaded</span>
    </div>
    <div class="panel pad metric">
      <span class="label">Pass count</span>
      <strong>{stats.passCount}</strong>
      <span>{stats.turnovers} turnovers detected in the canonical timeline</span>
    </div>
  </section>

  <section class="split" style="margin-bottom: 1rem;">
    <div class="panel pad stack">
      <div class="row" style="justify-content: space-between;">
        <div>
          <div class="eyebrow">Timeline Review</div>
          <h2>Per-point event stream</h2>
        </div>
        <button class="btn secondary" type="button" on:click={refreshAll} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {#if groupedEvents.length === 0}
        <div class="note">
          Waiting for canonical events. If the job is still running, this room keeps polling every few
          seconds.
        </div>
      {:else}
        {#each groupedEvents as pointGroup}
          <div class="timeline-point">
            <div class="row" style="justify-content: space-between; margin-bottom: 0.5rem;">
              <strong>Point {pointGroup.pointOrdinal}</strong>
              {#if pointsById.get(pointGroup.pointId)}
                <span class="tag">
                  {formatTimestamp(pointsById.get(pointGroup.pointId).start_video_ts_ms)} to
                  {formatTimestamp(pointsById.get(pointGroup.pointId).end_video_ts_ms)}
                </span>
              {/if}
            </div>

            {#each pointGroup.events as timelineEvent}
              <div class={`timeline-event ${selectedTimestamp === timelineEvent.video_ts_ms ? 'active' : ''}`}>
                <button type="button" on:click={() => selectTimestamp(timelineEvent.video_ts_ms)}>
                  <strong>{timelineEvent.type}</strong>
                  <div class="kicker">{timelineEvent.team} · point {timelineEvent.point_ordinal}</div>
                </button>
                <div class="subtle">
                  in-point {formatTimestamp(timelineEvent.in_point_ts_ms)}
                </div>
                <strong>{formatTimestamp(timelineEvent.video_ts_ms)}</strong>
              </div>
            {/each}
          </div>
        {/each}
      {/if}
    </div>

    <div class="stack">
      <section class="panel pad stack">
        <div class="eyebrow">Seek Target</div>
        <h3>Embedded scrub</h3>
        <div class="metric">
          <strong>{selectedTimestamp === null ? '--:--.-' : formatTimestamp(selectedTimestamp)}</strong>
          <span>Click any event in the timeline and the player seeks to that canonical timestamp.</span>
        </div>

        <video
          bind:this={videoElement}
          controls
          playsinline
          preload="metadata"
          src={videoSource}
          style="width: 100%; border-radius: 1rem; background: #102019;"
          on:error={() => (videoError = 'Video playback is not available for this game yet.')}
        >
          <track kind="captions" srclang="en" label="No captions available" src={emptyCaptions} default />
        </video>

        {#if videoError}
          <div class="error">{videoError}</div>
        {/if}
      </section>

      <section class="panel pad stack">
        <div class="eyebrow">Throw Mix</div>
        <h3>Current distribution</h3>
        {#if stats.throwTypeMix.length === 0}
          <div class="note">No throw-type annotations are available yet for this game.</div>
        {:else}
          {#each stats.throwTypeMix as [throwType, total]}
            <div class="row" style="justify-content: space-between;">
              <span class="tag">{throwType}</span>
              <strong>{total}</strong>
            </div>
          {/each}
        {/if}
      </section>

      {#if lastCorrection}
        <section class="success">
          Last correction saved for {lastCorrection.point_id}. Memory rows:
          {lastCorrection.created_memory_ids.join(', ') || 'none'}.
        </section>
      {/if}
    </div>
  </section>

  <section class="grid two">
    <PointBoundaryEditor gameId={gameId} points={points} onsaved={handleBoundarySaved} />
    <CorrectionDrawer gameId={gameId} points={points} events={events} onsubmitted={handleCorrectionSubmitted} />
  </section>
</div>
