<script>
  import { goto } from '$app/navigation';
  import { submitLocalGame, submitRemoteGame } from '$lib/api';

  let localFile = null;
  let localGameId = '';
  let remoteUrl = '';
  let remoteGameId = '';
  let callerId = 'web_alpha';
  let ackRights = false;
  let fps = 1;
  let submitting = false;
  let error = '';
  let latestJob = null;

  async function handleLocalSubmit(event) {
    event.preventDefault();
    if (!localFile) {
      error = 'Choose a local clip before submitting.';
      return;
    }

    submitting = true;
    error = '';
    try {
      latestJob = await submitLocalGame({
        upload: localFile,
        gameId: localGameId,
        fps
      });
      await goto(`/game/${latestJob.game_id}`);
    } catch (caught) {
      error = caught.message;
    } finally {
      submitting = false;
    }
  }

  async function handleRemoteSubmit(event) {
    event.preventDefault();
    submitting = true;
    error = '';
    try {
      latestJob = await submitRemoteGame({
        url: remoteUrl,
        ackRights,
        callerId,
        gameId: remoteGameId,
        fps
      });
      await goto(`/game/${latestJob.game_id}`);
    } catch (caught) {
      error = caught.message;
    } finally {
      submitting = false;
    }
  }
</script>

<div class="shell">
  <section class="hero">
    <span class="eyebrow">Phase 7 Alpha UI</span>
    <h1>Turn raw game film into a coach-ready event room.</h1>
    <p>
      Submit a clip or a rights-acknowledged public URL, then move straight into the point-scoped
      review flow. This shell talks to the existing async API and keeps the eval-gated alpha posture
      honest.
    </p>
  </section>

  {#if error}
    <div class="error" style="margin-bottom: 1rem;">{error}</div>
  {/if}

  <section class="grid two">
    <form class="panel pad stack" on:submit={handleLocalSubmit}>
      <div>
        <div class="eyebrow">Local Upload</div>
        <h2>Drop game film</h2>
      </div>

      <div class="field">
        <label for="local-upload">Video file</label>
        <input
          id="local-upload"
          type="file"
          accept=".mp4,.mov,.m4v,.webm"
          on:change={(event) => (localFile = event.currentTarget.files?.[0] || null)}
        />
      </div>

      <div class="grid two">
        <div class="field">
          <label for="local-game-id">Optional game ID</label>
          <input id="local-game-id" bind:value={localGameId} placeholder="game_alpha_001" />
        </div>
        <div class="field">
          <label for="fps">Sampling FPS</label>
          <input id="fps" type="number" min="1" max="3" bind:value={fps} />
        </div>
      </div>

      <div class="actions">
        <button class="btn primary" type="submit" disabled={submitting}>
          {submitting ? 'Submitting...' : 'Queue local ingest'}
        </button>
      </div>
    </form>

    <form class="panel pad stack" on:submit={handleRemoteSubmit}>
      <div>
        <div class="eyebrow">Public URL</div>
        <h2>Pull from the web</h2>
      </div>

      <div class="field">
        <label for="remote-url">Approved public URL</label>
        <input id="remote-url" bind:value={remoteUrl} placeholder="https://www.youtube.com/watch?v=..." required />
      </div>

      <div class="grid two">
        <div class="field">
          <label for="caller-id">Caller ID</label>
          <input id="caller-id" bind:value={callerId} required />
        </div>
        <div class="field">
          <label for="remote-game-id">Optional game ID</label>
          <input id="remote-game-id" bind:value={remoteGameId} placeholder="game_alpha_002" />
        </div>
      </div>

      <label class="row">
        <input type="checkbox" bind:checked={ackRights} />
        <span>I acknowledge rights before remote ingest runs.</span>
      </label>

      <div class="actions">
        <button class="btn primary" type="submit" disabled={submitting || !ackRights}>
          {submitting ? 'Submitting...' : 'Queue remote ingest'}
        </button>
      </div>
    </form>
  </section>

  <section class="grid two" style="margin-top: 1rem;">
    <div class="panel pad stack">
      <div class="eyebrow">Coach Workflow</div>
      <h3>What happens next</h3>
      <div class="note">
        Upload or URL intake lands in the async job queue, point detection runs before perception,
        then the game room polls status, shows the canonical event timeline, and unlocks corrections
        plus point-boundary edits.
      </div>
    </div>

    <div class="panel pad stack">
      <div class="eyebrow">Alpha Guardrails</div>
      <h3>Still honest about the blockers</h3>
      <div class="note">
        The UI is live, but alpha readiness is still blocked on the real gold set and independent
        annotator coverage. The new eval harness keeps that gate explicit instead of hand-waving it.
      </div>

      {#if latestJob}
        <div class="success">
          Latest job queued: <strong>{latestJob.game_id}</strong>
        </div>
      {/if}
    </div>
  </section>
</div>
