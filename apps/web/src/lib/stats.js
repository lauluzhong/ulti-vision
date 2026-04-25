export function summarizeGameStats(events) {
  const completions = events.filter((event) => event.type === 'completion').length;
  const turnovers = events.filter((event) => event.type === 'turnover').length;
  const goals = events.filter((event) => event.type === 'goal').length;
  const passCount = completions;
  const attempts = completions + turnovers;
  const completionRate = attempts > 0 ? Math.round((completions / attempts) * 100) : 0;

  const throwTypeMix = events.reduce((accumulator, event) => {
    if (!event.throw_type) {
      return accumulator;
    }
    accumulator[event.throw_type] = (accumulator[event.throw_type] || 0) + 1;
    return accumulator;
  }, {});

  return {
    completions,
    turnovers,
    goals,
    passCount,
    completionRate,
    throwTypeMix: Object.entries(throwTypeMix).sort((left, right) => right[1] - left[1])
  };
}

export function groupEventsByPoint(events) {
  const groups = new Map();
  for (const event of events) {
    if (!groups.has(event.point_id)) {
      groups.set(event.point_id, {
        pointId: event.point_id,
        pointOrdinal: event.point_ordinal,
        events: []
      });
    }
    groups.get(event.point_id).events.push(event);
  }
  return [...groups.values()].sort((left, right) => left.pointOrdinal - right.pointOrdinal);
}

export function formatTimestamp(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const tenths = Math.floor((ms % 1000) / 100);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${tenths}`;
}
