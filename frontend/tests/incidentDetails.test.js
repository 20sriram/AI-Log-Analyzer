import assert from "node:assert/strict";
import test from "node:test";

import { buildIncidentDetails } from "../src/incidentDetails.js";

const makeEvent = (overrides = {}) => ({
  id: 1,
  timestamp: "2026-10-22 10:00:00",
  service: "payment",
  level: "ERROR",
  message: "Payment request failed",
  ...overrides
});

test("builds investigation details from existing database analysis", () => {
  const detail = buildIncidentDetails({
    analyzed_logs: [makeEvent({ anomaly: true })],
    related_events: [makeEvent()],
    probable_root_cause: makeEvent(),
    severity: "HIGH",
    confidence: 0.7,
    explanation: "A heuristic candidate; correlation is not proof."
  });

  assert.equal(detail.source, "Database log analysis");
  assert.equal(detail.title, "Incident: Payment request failed");
  assert.equal(detail.severity, "HIGH");
  assert.equal(detail.confidence, 0.7);
  assert.equal(detail.rootCause.id, 1);
  assert.equal(detail.timeline.length, 1);
  assert.equal(detail.timeline[0].isProbableRootCause, true);
  assert.equal(detail.anomalies.length, 1);
  assert.deepEqual(detail.affectedServices, ["payment"]);
  assert.equal(detail.startTimestamp, "2026-10-22 10:00:00");
  assert.equal(detail.endTimestamp, detail.startTimestamp);
});

test("sorts chronologically and removes duplicate event IDs", () => {
  const detail = buildIncidentDetails({
    related_events: [
      makeEvent({ id: 2, timestamp: "2026-10-22 10:00:03", message: "second" }),
      makeEvent({ id: 1, timestamp: "2026-10-22 10:00:01", message: "first" }),
      makeEvent({ id: 1, timestamp: "2026-10-22 10:00:01", message: "duplicate" }),
      makeEvent({ id: 3, timestamp: null, message: "unknown time" })
    ]
  });

  assert.deepEqual(detail.timeline.map((event) => event.id), [1, 2, 3]);
  assert.deepEqual(
    detail.timeline.map((event) => event.message),
    ["first", "second", "unknown time"]
  );
  assert.equal(detail.timeline[2].timestamp, null);
});

test("deduplicates identical events without IDs and associates only linked anomalies", () => {
  const anonymousEvent = makeEvent({ id: undefined, message: "repeated event" });
  const detail = buildIncidentDetails({
    analyzed_logs: [
      { ...anonymousEvent, anomaly: true },
      makeEvent({ id: 99, anomaly: true, message: "unrelated anomaly" })
    ],
    related_events: [anonymousEvent, { ...anonymousEvent }]
  });

  assert.equal(detail.timeline.length, 1);
  assert.equal(detail.anomalies.length, 1);
  assert.equal(detail.anomalies[0].message, "repeated event");
});

test("keeps incomplete events visible and reports unavailable fields", () => {
  const detail = buildIncidentDetails({
    related_events: [{ id: 10, timestamp: "invalid", service: " ", message: "" }],
    probable_root_cause: null
  });

  assert.equal(detail.title, "Incident with 1 observed event");
  assert.equal(detail.timeline.length, 1);
  assert.equal(detail.timeline[0].timestampAvailable, false);
  assert.equal(detail.startTimestamp, null);
  assert.equal(detail.endTimestamp, null);
  assert.deepEqual(detail.affectedServices, []);
  assert.equal(detail.rootCause, null);
  assert.equal(detail.severity, null);
  assert.equal(detail.confidence, null);
});

test("keeps recovery events separate and identifies upload source", () => {
  const detail = buildIncidentDetails({
    related_events: [makeEvent()],
    recovery_events: [
      makeEvent({
        id: 2,
        timestamp: "2026-10-22 10:00:08",
        level: "INFO",
        message: "Payment service recovered"
      })
    ],
    analyzed_logs: [makeEvent({ anomaly: true })],
    probable_root_cause: makeEvent()
  }, { source: "upload", filename: "incident.log" });

  assert.equal(detail.source, "Uploaded file: incident.log");
  assert.equal(detail.timeline.length, 2);
  assert.equal(detail.recoveryEvents.length, 1);
  assert.equal(detail.recoveryEvents[0].kind, "recovery");
  assert.equal(detail.anomalies.length, 1);
});

test("supports incidents without recovery and unavailable root causes", () => {
  const detail = buildIncidentDetails({
    related_events: [makeEvent({ id: 4 })],
    recovery_events: [],
    probable_root_cause: null,
    explanation: "No probable root cause was selected."
  });

  assert.equal(detail.rootCause, null);
  assert.equal(detail.recoveryEvents.length, 0);
  assert.equal(detail.explanation, "No probable root cause was selected.");
});

test("returns an honest empty investigation when analysis data is missing", () => {
  const detail = buildIncidentDetails(null);

  assert.equal(detail.source, "Database log analysis");
  assert.equal(detail.title, "Incident details unavailable");
  assert.equal(detail.rootCause, null);
  assert.equal(detail.severity, null);
  assert.equal(detail.confidence, null);
  assert.equal(detail.explanation, null);
  assert.deepEqual(detail.timeline, []);
  assert.deepEqual(detail.anomalies, []);
  assert.deepEqual(detail.recoveryEvents, []);
  assert.deepEqual(detail.affectedServices, []);
  assert.equal(detail.startTimestamp, null);
  assert.equal(detail.endTimestamp, null);
});