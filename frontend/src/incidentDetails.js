const parseTimestamp = (timestamp) => {
  if (typeof timestamp !== "string" || timestamp.trim() === "") {
    return null;
  }

  const normalized = timestamp.replace(
    /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})$/,
    "$1T$2"
  );
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? null : parsed;
};

const eventKey = (event) => {
  if (event.id !== undefined && event.id !== null) {
    return `id:${String(event.id)}`;
  }

  return `fields:${JSON.stringify([
    event.timestamp ?? null,
    event.service ?? null,
    event.level ?? null,
    event.message ?? null
  ])}`;
};

const displayService = (service) => (
  typeof service === "string" && service.trim() !== ""
    ? service.trim()
    : null
);

export function buildIncidentDetails(
  analysis,
  { source = "database", filename = null } = {}
) {
  const relatedEvents = Array.isArray(analysis?.related_events)
    ? analysis.related_events
    : [];
  const recoveryEvents = Array.isArray(analysis?.recovery_events)
    ? analysis.recovery_events
    : [];
  const analyzedLogs = Array.isArray(analysis?.analyzed_logs)
    ? analysis.analyzed_logs
    : [];

  const eventsByKey = new Map();
  relatedEvents.forEach((event) => {
    if (event && typeof event === "object") {
      const key = eventKey(event);
      if (!eventsByKey.has(key)) {
        eventsByKey.set(key, { ...event, kind: "incident" });
      }
    }
  });
  recoveryEvents.forEach((event) => {
    if (event && typeof event === "object") {
      const key = eventKey(event);
      const existing = eventsByKey.get(key);
      eventsByKey.set(key, {
        ...(existing ?? event),
        kind: "recovery"
      });
    }
  });

  const anomalyKeys = new Set(
    analyzedLogs
      .filter((log) => log && log.anomaly === true)
      .map(eventKey)
  );
  const rootCause = analysis?.probable_root_cause
    && typeof analysis.probable_root_cause === "object"
    ? analysis.probable_root_cause
    : null;
  const rootCauseKey = rootCause ? eventKey(rootCause) : null;

  const timeline = [...eventsByKey.entries()]
    .map(([key, event], index) => ({
      event: {
        ...event,
        key,
        timestampAvailable: parseTimestamp(event.timestamp) !== null,
        anomaly: anomalyKeys.has(key),
        isProbableRootCause: key === rootCauseKey
      },
      parsedTimestamp: parseTimestamp(event.timestamp),
      originalIndex: index
    }))
    .sort((first, second) => {
      if (first.parsedTimestamp === null && second.parsedTimestamp !== null) {
        return 1;
      }
      if (first.parsedTimestamp !== null && second.parsedTimestamp === null) {
        return -1;
      }
      if (
        first.parsedTimestamp !== null
        && second.parsedTimestamp !== null
        && first.parsedTimestamp !== second.parsedTimestamp
      ) {
        return first.parsedTimestamp - second.parsedTimestamp;
      }
      return first.originalIndex - second.originalIndex;
    })
    .map(({ event }) => event);

  const observedServices = [
    ...new Set(
      timeline
        .map((event) => displayService(event.service))
        .filter(Boolean)
    )
  ].sort((first, second) => first.localeCompare(second));
  const timestampedEvents = timeline.filter(
    (event) => parseTimestamp(event.timestamp) !== null
  );
  const rootCauseMessage = displayService(rootCause?.message);

  return {
    source: source === "upload" && filename
      ? `Uploaded file: ${filename}`
      : "Database log analysis",
    title: rootCauseMessage
      ? `Incident: ${rootCauseMessage}`
      : timeline.length > 0
      ? `Incident with ${timeline.length} observed event${timeline.length === 1 ? "" : "s"}`
      : "Incident details unavailable",
    severity: typeof analysis?.severity === "string" ? analysis.severity : null,
    confidence: Number.isFinite(analysis?.confidence)
      ? analysis.confidence
      : null,
    rootCause,
    explanation: typeof analysis?.explanation === "string"
      ? analysis.explanation
      : null,
    timeline,
    anomalies: timeline.filter((event) => event.anomaly),
    recoveryEvents: timeline.filter((event) => event.kind === "recovery"),
    affectedServices: observedServices,
    startTimestamp: timestampedEvents.length > 0
      ? timestampedEvents[0].timestamp
      : null,
    endTimestamp: timestampedEvents.length > 0
      ? timestampedEvents[timestampedEvents.length - 1].timestamp
      : null
  };
}