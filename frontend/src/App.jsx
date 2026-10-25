import { useEffect, useRef, useState } from "react";
import { buildIncidentDetails } from "./incidentDetails";
import "./App.css";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const MAX_UPLOAD_SIZE_BYTES = 2 * 1024 * 1024;

const MISSING_SERVICE_KEY = "missing-service";

const getServiceKey = (service) => {
  if (typeof service !== "string" || service.trim() === "") {
    return MISSING_SERVICE_KEY;
  }

  return `service:${service.trim().toLowerCase()}`;
};

const escapeCsvValue = (value) => {
  const text = value == null ? "" : String(value);
  const safeText = /^[\t\r\n ]*[=+\-@]/.test(text) ? `'${text}` : text;

  return `"${safeText.replace(/"/g, '""')}"`;
};

const getEventTime = (timestamp) => {
  if (typeof timestamp !== "string" || timestamp.trim() === "") {
    return null;
  }

  const normalizedTimestamp = timestamp.replace(
    /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})$/,
    "$1T$2"
  );
  const eventTime = Date.parse(normalizedTimestamp);

  return Number.isNaN(eventTime) ? null : eventTime;
};

const selectTrendBuckets = (analytics, range, now) => {
  const rangeMilliseconds = range === "1h"
    ? 60 * 60 * 1000
    : range === "24h"
    ? 24 * 60 * 60 * 1000
    : null;

  return (analytics?.time_buckets ?? [])
    .map((bucket) => ({ bucket, time: getEventTime(bucket.start) }))
    .filter(({ time }) => (
      time !== null
      && time <= now
      && (rangeMilliseconds === null || time >= now - rangeMilliseconds)
    ))
    .map(({ bucket, time }) => ({
      ...bucket,
      label: new Date(time).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
      })
    }));
};

function TrendChart({ title, buckets, series }) {
  const chartWidth = 720;
  const chartHeight = 220;
  const plotLeft = 42;
  const plotRight = 12;
  const plotTop = 12;
  const plotBottom = 28;
  const plotWidth = chartWidth - plotLeft - plotRight;
  const plotHeight = chartHeight - plotTop - plotBottom;
  const maxValue = Math.max(
    1,
    ...buckets.flatMap((bucket) => series.map(({ key }) => bucket[key]))
  );
  const getX = (index) => (
    plotLeft + (buckets.length < 2 ? plotWidth / 2 : index * plotWidth / (buckets.length - 1))
  );
  const getY = (value) => plotTop + plotHeight - (value / maxValue) * plotHeight;

  return (
    <div className="trend-chart">
      <h3>{title}</h3>
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        role="img"
        aria-label={title}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
          const y = plotTop + plotHeight * fraction;
          return (
            <line
              key={fraction}
              className="trend-gridline"
              x1={plotLeft}
              x2={chartWidth - plotRight}
              y1={y}
              y2={y}
            />
          );
        })}
        {series.map(({ key, color, label }) => {
          const points = buckets.map((bucket, index) => (
            `${getX(index)},${getY(bucket[key])}`
          )).join(" ");

          return (
            <g key={key}>
              <polyline
                className="trend-line"
                points={points}
                stroke={color}
              />
              {buckets.map((bucket, index) => (
                <circle
                  key={`${key}-${bucket.start}`}
                  className="trend-point"
                  cx={getX(index)}
                  cy={getY(bucket[key])}
                  r="3"
                  fill={color}
                >
                  <title>{`${bucket.label}: ${bucket[key]} ${label}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        <text className="trend-axis-label" x={plotLeft} y={chartHeight - 5}>
          {buckets[0]?.label}
        </text>
        <text
          className="trend-axis-label"
          x={chartWidth - plotRight}
          y={chartHeight - 5}
          textAnchor="end"
        >
          {buckets[buckets.length - 1]?.label}
        </text>
      </svg>
      <div className="trend-legend">
        {series.map(({ key, color, label }) => (
          <span key={key}>
            <i style={{ backgroundColor: color }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

function SeverityDistributionChart({ counts }) {
  const severities = [
    { name: "INFO", color: "#16a34a" },
    { name: "WARNING", color: "#d97706" },
    { name: "ERROR", color: "#dc2626" },
    { name: "UNKNOWN", color: "#64748b" }
  ].filter(({ name }) => name !== "UNKNOWN" || counts.UNKNOWN > 0);
  const maxCount = Math.max(1, ...severities.map(({ name }) => counts[name]));

  return (
    <div className="severity-bar-chart" role="img" aria-label="Log counts by severity">
      {severities.map(({ name, color }) => (
        <div className="severity-bar-row" key={name}>
          <div className="severity-bar-label">
            <span>{name}</span>
            <strong>{counts[name]}</strong>
          </div>
          <div className="severity-bar-track">
            <span
              style={{
                width: `${(counts[name] / maxCount) * 100}%`,
                backgroundColor: color
              }}
              title={`${name}: ${counts[name]} logs`}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function AnomalySummaryChart({ summary }) {
  const total = summary.anomalies + summary.normal;
  const anomalyPercent = total > 0 ? (summary.anomalies / total) * 100 : 0;

  return (
    <div className="anomaly-summary-chart">
      <div
        className="anomaly-summary-track"
        role="img"
        aria-label={`${summary.anomalies} anomalous logs and ${summary.normal} normal logs from database analysis`}
        title={`${summary.anomalies} anomalies · ${summary.normal} normal logs`}
      >
        <span style={{ width: `${anomalyPercent}%` }} />
      </div>
      <div className="anomaly-summary-legend">
        <span>
          <i className="anomaly-legend-swatch" />
          Anomalies <strong>{summary.anomalies}</strong>
        </span>
        <span>
          <i className="normal-legend-swatch" />
          Normal <strong>{summary.normal}</strong>
        </span>
      </div>
    </div>
  );
}

function UploadEventSection({ title, events, emptyMessage, eventKind }) {
  return (
    <section className={`upload-event-section ${eventKind}`}>
      <div className="upload-event-heading">
        <h3>{title}</h3>
        <span>{events.length}</span>
      </div>
      {events.length === 0 ? (
        <p className="upload-event-empty">{emptyMessage}</p>
      ) : (
        <ol className="upload-event-list">
          {events.map((event, index) => {
            const level = typeof event.level === "string"
              ? event.level.toUpperCase()
              : "UNKNOWN";
            return (
              <li className="upload-event-row" key={event.id ?? `${eventKind}-${index}`}>
                <div className="upload-event-meta">
                  <time>
                    {typeof event.timestamp === "string" && event.timestamp.trim()
                      ? event.timestamp
                      : "Timestamp unavailable"}
                  </time>
                  <span className={`upload-severity ${level.toLowerCase()}`}>
                    {level}
                  </span>
                  <span className="upload-event-service">
                    {event.service || "Service unavailable"}
                  </span>
                </div>
                <p>{event.message || "Message unavailable"}</p>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function App() {
  const [logsState, setLogsState] = useState({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [analysisState, setAnalysisState] = useState({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [serviceHealthState, setServiceHealthState] = useState({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [analyticsState, setAnalyticsState] = useState({
    data: null,
    loading: true,
    error: null,
    updatedAt: null
  });
  const [backendStatus, setBackendStatus] = useState("checking");
  const [uploadState, setUploadState] = useState({
    file: null,
    loading: false,
    error: null,
    result: null
  });
  const [uploadDropActive, setUploadDropActive] = useState(false);
  const [logSearch, setLogSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [serviceFilter, setServiceFilter] = useState("ALL");
  const [trendRange, setTrendRange] = useState("24h");
  const [activePage, setActivePage] = useState("live");
  const [activeSection, setActiveSection] = useState("dashboard");
  const [selectedLog, setSelectedLog] = useState(null);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const analysisSectionRef = useRef(null);
  const logsSectionRef = useRef(null);
  const detailCloseButtonRef = useRef(null);
  const detailTriggerRef = useRef(null);
  const incidentCloseButtonRef = useRef(null);
  const incidentTriggerRef = useRef(null);
  const uploadInputRef = useRef(null);
  const uploadDragDepthRef = useRef(0);

  useEffect(() => {
    if (selectedLog) {
      detailCloseButtonRef.current?.focus();
    }
  }, [selectedLog]);

  useEffect(() => {
    if (selectedIncident) {
      incidentCloseButtonRef.current?.focus();
    }
  }, [selectedIncident]);

  useEffect(() => {
    let isActive = true;
    let isFetching = false;

    const fetchJson = async (path) => {
      let response;
      try {
        response = await fetch(`${API_BASE_URL}${path}`);
      } catch {
        throw new Error(
          "Could not connect to the API. Check that the backend is running and the API URL is correct."
        );
      }

      if (!response.ok) {
        const error = new Error(
          `The server returned HTTP ${response.status} ${response.statusText}.`
        );
        error.backendResponded = true;
        throw error;
      }

      try {
        return await response.json();
      } catch {
        const error = new Error("The server returned an invalid JSON response.");
        error.backendResponded = true;
        throw error;
      }
    };

    const updateRequestState = (result, setState, validateData, name) => {
      if (result.status === "fulfilled") {
        try {
          validateData(result.value);
          setState({
            data: result.value,
            loading: false,
            error: null,
            updatedAt: Date.now()
          });
        } catch (error) {
          setState((previous) => ({
            ...previous,
            loading: false,
            error: `${name} response was invalid: ${error.message}`
          }));
        }
        return;
      }

      const message = result.reason instanceof Error
        ? result.reason.message
        : "An unexpected request error occurred.";
      setState((previous) => ({
        ...previous,
        loading: false,
        error: message
      }));
    };

    const fetchData = async () => {
      if (isFetching) {
        return;
      }
      isFetching = true;

      try {
        const [logsResult, analysisResult, serviceHealthResult, analyticsResult] = await Promise.allSettled([
          fetchJson("/logs"),
          fetchJson("/logs/analyze"),
          fetchJson("/services/health"),
          fetchJson("/logs/analytics")
        ]);

        if (!isActive) {
          return;
        }

        const results = [
          logsResult,
          analysisResult,
          serviceHealthResult,
          analyticsResult
        ];
        const backendResponded = results.some(
          (result) =>
            result.status === "fulfilled" || result.reason?.backendResponded
        );
        setBackendStatus(backendResponded ? "online" : "offline");

        updateRequestState(
          logsResult,
          setLogsState,
          (data) => {
            if (!Array.isArray(data)) {
              throw new Error("expected a list of log records");
            }
          },
          "Logs"
        );
        updateRequestState(
          analysisResult,
          setAnalysisState,
          (data) => {
            if (
              !data
              || !Array.isArray(data.analyzed_logs)
              || !Array.isArray(data.related_events)
              || !("probable_root_cause" in data)
              || (
                data.probable_root_cause !== null
                && (
                  typeof data.probable_root_cause !== "object"
                  || Array.isArray(data.probable_root_cause)
                )
              )
              || typeof data.severity !== "string"
              || typeof data.confidence !== "number"
              || typeof data.explanation !== "string"
            ) {
              throw new Error("missing or invalid analysis fields");
            }
          },
          "Analysis"
        );
        updateRequestState(
          serviceHealthResult,
          setServiceHealthState,
          (data) => {
            if (
              !Array.isArray(data)
              || data.some((service) => (
                !service
                || !(service.service === null || typeof service.service === "string")
                || !Number.isInteger(service.total_logs)
                || !Number.isInteger(service.error_count)
                || !Number.isInteger(service.warning_count)
                || !(
                  service.most_recent_timestamp === null
                  || typeof service.most_recent_timestamp === "string"
                )
                || !["Healthy", "Warning", "Critical"].includes(service.health_status)
              ))
            ) {
              throw new Error("expected valid service health records");
            }
          },
          "Service health"
        );
        updateRequestState(
          analyticsResult,
          setAnalyticsState,
          (data) => {
            if (
              !data
              || !Number.isInteger(data.total_logs)
              || !data.severity_counts
              || !["INFO", "WARNING", "ERROR", "UNKNOWN"].every(
                (level) => Number.isInteger(data.severity_counts[level])
              )
              || !Number.isInteger(data.invalid_timestamp_count)
              || !Array.isArray(data.time_buckets)
              || !Array.isArray(data.log_ids)
              || data.time_buckets.some((bucket) => (
                typeof bucket.start !== "string"
                || !Number.isInteger(bucket.count)
              ))
            ) {
              throw new Error("expected valid database analytics");
            }
          },
          "Log analytics"
        );
      } finally {
        isFetching = false;
      }
    };

    fetchData();

    const interval = setInterval(fetchData, 2000);

    return () => {
      isActive = false;
      clearInterval(interval);
    };
  }, []);

  const logs = logsState.data || [];
  const analytics = analyticsState.data;
  const trendBuckets = selectTrendBuckets(
    analytics,
    trendRange,
    analyticsState.updatedAt ?? 0
  );
  const serviceHealth = serviceHealthState.data || [];
  const analysis = analysisState.data;
  const anomalySummary = (() => {
    if (!analytics || !analysis || !Array.isArray(analysis.analyzed_logs)) {
      return null;
    }

    const databaseIds = new Set(analytics.log_ids);
    const analyzedIds = new Set(
      analysis.analyzed_logs.map((log) => log.id)
    );
    if (
      analytics.total_logs !== analytics.log_ids.length
      || analyzedIds.size !== analysis.analyzed_logs.length
      || databaseIds.size !== analyzedIds.size
      || [...databaseIds].some((id) => !analyzedIds.has(id))
      || analysis.analyzed_logs.some((log) => typeof log.anomaly !== "boolean")
    ) {
      return null;
    }

    const anomalies = analysis.analyzed_logs.filter((log) => log.anomaly).length;
    return {
      anomalies,
      normal: analysis.analyzed_logs.length - anomalies
    };
  })();
  const analyzedLogs = analysis?.analyzed_logs ?? logs;
  const normalizedSearch = logSearch.trim().toLowerCase();
  const filteredLogs = analyzedLogs.filter((log) => {
    const matchesSearch = normalizedSearch === ""
      || String(log.message ?? "").toLowerCase().includes(normalizedSearch)
      || String(log.service ?? "").toLowerCase().includes(normalizedSearch);
    const matchesSeverity =
      severityFilter === "ALL" || log.level === severityFilter;
    const matchesService =
      serviceFilter === "ALL" || getServiceKey(log.service) === serviceFilter;

    return matchesSearch && matchesSeverity && matchesService;
  });
  const visibleLogs = activeSection === "anomalies"
    ? filteredLogs.filter((log) => log.anomaly)
    : filteredLogs;
  const timelineEvents = (analysis?.related_events ?? [])
    .map((event, index) => ({
      event,
      index,
      timestamp: getEventTime(event.timestamp)
    }))
    .sort((first, second) => {
      if (first.timestamp === null && second.timestamp !== null) {
        return 1;
      }
      if (first.timestamp !== null && second.timestamp === null) {
        return -1;
      }
      if (first.timestamp === null || second.timestamp === null) {
        return first.index - second.index;
      }
      return first.timestamp - second.timestamp || first.index - second.index;
    })
    .map(({ event }) => event);
  const relatedEvents = analysis?.related_events ?? [];
  const affectedServices = [
    ...new Map(
      relatedEvents
        .filter((event) => typeof event.service === "string" && event.service.trim())
        .map((event) => [event.service.trim().toLowerCase(), event.service.trim()])
    ).values()
  ];
  const relatedErrorCount = relatedEvents.filter(
    (event) => event.level === "ERROR"
  ).length;
  const relatedWarningCount = relatedEvents.filter(
    (event) => event.level === "WARNING"
  ).length;
  const hasIncidentData =
    relatedEvents.length > 0 || Boolean(analysis?.probable_root_cause);
  const impactRecommendations = [];

  if (analysis?.probable_root_cause) {
    const rootCause = analysis.probable_root_cause;
    const rootCauseDescription = [
      rootCause.level,
      rootCause.service,
      rootCause.message
    ].filter(Boolean).join(" — ");

    impactRecommendations.push(
      `Review the probable root-cause event${rootCauseDescription ? ` (${rootCauseDescription})` : ""} against the surrounding timeline. Treat it as a lead, not a confirmed cause.`
    );
  }
  if (relatedErrorCount > 0) {
    impactRecommendations.push(
      `Inspect the ${relatedErrorCount} related ERROR event${relatedErrorCount === 1 ? "" : "s"} and compare their timestamps and messages with nearby logs.`
    );
  }
  if (relatedWarningCount > 0) {
    impactRecommendations.push(
      `Review the ${relatedWarningCount} related WARNING event${relatedWarningCount === 1 ? "" : "s"} for context around the incident sequence.`
    );
  }
  if (affectedServices.length > 1) {
    impactRecommendations.push(
      `Compare the event sequence across the ${affectedServices.length} affected services (${affectedServices.join(", ")}) to identify where follow-up investigation is needed.`
    );
  }

  const navigateTo = (section) => {
    setActivePage("live");
    setActiveSection(section);

    if (section === "dashboard") {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    const target = section === "root-cause"
      ? analysisSectionRef.current
      : logsSectionRef.current;
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const openLogDetails = (log, event) => {
    detailTriggerRef.current = event.currentTarget;
    setSelectedLog(log);
  };

  const openIncidentInvestigation = (incidentAnalysis, source, filename, event) => {
    incidentTriggerRef.current = event.currentTarget;
    setSelectedIncident(buildIncidentDetails(incidentAnalysis, {
      source,
      filename
    }));
  };

  const closeIncidentInvestigation = () => {
    setSelectedIncident(null);
    incidentTriggerRef.current?.focus();
  };

  const handleIncidentDialogKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeIncidentInvestigation();
    } else if (event.key === "Tab") {
      event.preventDefault();
      incidentCloseButtonRef.current?.focus();
    }
  };

  const closeLogDetails = () => {
    setSelectedLog(null);
    detailTriggerRef.current?.focus();
  };

  const handleLogDetailsKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeLogDetails();
    } else if (event.key === "Tab") {
      event.preventDefault();
      detailCloseButtonRef.current?.focus();
    }
  };

  const exportVisibleLogs = () => {
    if (visibleLogs.length === 0) {
      return;
    }

    const includeAnomaly = visibleLogs.some(
      (log) => typeof log.anomaly === "boolean"
    );
    const headers = ["timestamp", "service", "level", "message"];
    if (includeAnomaly) {
      headers.push("anomaly");
    }

    const rows = visibleLogs.map((log) => {
      const values = [log.timestamp, log.service, log.level, log.message];
      if (includeAnomaly) {
        values.push(typeof log.anomaly === "boolean" ? log.anomaly : "");
      }
      return values;
    });
    const csv = `\uFEFF${[headers, ...rows]
      .map((row) => row.map(escapeCsvValue).join(","))
      .join("\r\n")}`;
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "recent-logs.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const validateUploadFile = (file) => {
    if (!file) {
      return "Choose a .log or .txt file to analyze.";
    }
    if (!/\.(log|txt)$/i.test(file.name)) {
      return "Only .log and .txt files are supported.";
    }
    if (file.size > MAX_UPLOAD_SIZE_BYTES) {
      return "The selected file exceeds the 2 MiB limit.";
    }
    return null;
  };

  const selectUploadFile = (file) => {
    setUploadState({
      file,
      loading: false,
      error: validateUploadFile(file),
      result: null
    });
  };

  const handleUploadFileChange = (event) => {
    selectUploadFile(event.target.files?.[0] ?? null);
  };

  const handleUploadDrop = (event) => {
    event.preventDefault();
    uploadDragDepthRef.current = 0;
    setUploadDropActive(false);
    selectUploadFile(event.dataTransfer.files?.[0] ?? null);
  };

  const clearUploadFile = () => {
    if (uploadInputRef.current) {
      uploadInputRef.current.value = "";
    }
    setUploadState({ file: null, loading: false, error: null, result: null });
  };

  const analyzeUploadedFile = async (event) => {
    event.preventDefault();
    const file = uploadState.file;
    const validationError = validateUploadFile(file);
    if (validationError) {
      setUploadState((previous) => ({
        ...previous,
        error: validationError,
        result: null
      }));
      return;
    }

    setUploadState((previous) => ({
      ...previous,
      loading: true,
      error: null,
      result: null
    }));

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE_URL}/logs/analyze-file`, {
        method: "POST",
        body: formData
      });
      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new Error("The API returned an invalid response.");
      }
      if (!response.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : `The server returned HTTP ${response.status}.`
        );
      }
      if (
        !payload
        || !Array.isArray(payload.analyzed_logs)
        || !Array.isArray(payload.detected_anomalies)
        || !Array.isArray(payload.related_events)
        || !Array.isArray(payload.recovery_events)
        || !Array.isArray(payload.rejected_lines)
      ) {
        throw new Error("The API returned an incomplete analysis result.");
      }

      setUploadState((previous) => ({
        ...previous,
        loading: false,
        result: payload
      }));
    } catch (error) {
      setUploadState((previous) => ({
        ...previous,
        loading: false,
        error: error instanceof Error
          ? error.message
          : "The uploaded file could not be analyzed."
      }));
    }
  };

  const totalLogs = logs.length;
  const infoLogs = logs.filter((log) => log.level === "INFO").length;
  const warningLogs = logs.filter((log) => log.level === "WARNING").length;
  const errorLogs = logs.filter((log) => log.level === "ERROR").length;

  return (
    <div className="dashboard">

      <aside className="sidebar">

        <div className="logo">
          <div className="logo-icon">AI</div>

          <div>
            <h2>Log Analyzer</h2>
            <span>AI Monitoring</span>
          </div>
        </div>

        <nav className="page-nav" aria-label="Primary navigation">
          <button
            type="button"
            className={`menu ${activePage === "live" ? "active" : ""}`}
            aria-current={activePage === "live" ? "page" : undefined}
            onClick={() => {
              setActivePage("live");
              setActiveSection("dashboard");
            }}
          >
            <span>◉</span>
            Live Monitoring
          </button>
          <button
            type="button"
            className={`menu ${activePage === "upload" ? "active" : ""}`}
            aria-current={activePage === "upload" ? "page" : undefined}
            onClick={() => setActivePage("upload")}
          >
            <span>↑</span>
            Upload &amp; Analyze
          </button>
        </nav>

        {activePage === "live" && (
          <nav className="section-nav" aria-label="Live Monitoring sections">
            <button
              type="button"
              className={`menu ${activeSection === "dashboard" ? "active" : ""}`}
              aria-current={activeSection === "dashboard" ? "location" : undefined}
              onClick={() => navigateTo("dashboard")}
            >
              Overview
            </button>
            <button
              type="button"
              className={`menu ${activeSection === "logs" ? "active" : ""}`}
              aria-current={activeSection === "logs" ? "location" : undefined}
              onClick={() => navigateTo("logs")}
            >
              Log table
            </button>
            <button
              type="button"
              className={`menu ${activeSection === "anomalies" ? "active" : ""}`}
              aria-current={activeSection === "anomalies" ? "location" : undefined}
              onClick={() => navigateTo("anomalies")}
            >
              Anomalies
            </button>
            <button
              type="button"
              className={`menu ${activeSection === "root-cause" ? "active" : ""}`}
              aria-current={activeSection === "root-cause" ? "location" : undefined}
              onClick={() => navigateTo("root-cause")}
            >
              Root Cause
            </button>
          </nav>
        )}

        <div className="sidebar-bottom">
          <div className={`system-online ${backendStatus}`}>
            <span></span>
            {backendStatus === "online"
              ? "System Online"
              : backendStatus === "offline"
              ? "System Offline"
              : "Checking Backend"}
          </div>
        </div>

      </aside>

      <main className="main-content">

        <header className="topbar">

          <div>
            <h1>{activePage === "live" ? "Live Monitoring" : "Upload & Analyze"}</h1>
            <p>
              {activePage === "live"
                ? "Database logs, service health, and incident activity"
                : "Analyze a log file independently from database monitoring"}
            </p>
          </div>

          <div className={`monitoring ${backendStatus}`}>
            <span className={`pulse ${backendStatus}`}></span>
            {backendStatus === "online"
              ? "Monitoring"
              : backendStatus === "offline"
              ? "Backend Offline"
              : "Checking Backend"}
          </div>

        </header>

        <nav className="mobile-page-nav" aria-label="Primary navigation">
          <button
            type="button"
            className={activePage === "live" ? "active" : ""}
            aria-current={activePage === "live" ? "page" : undefined}
            onClick={() => {
              setActivePage("live");
              setActiveSection("dashboard");
            }}
          >
            Live Monitoring
          </button>
          <button
            type="button"
            className={activePage === "upload" ? "active" : ""}
            aria-current={activePage === "upload" ? "page" : undefined}
            onClick={() => setActivePage("upload")}
          >
            Upload &amp; Analyze
          </button>
        </nav>

        {activePage === "live" && (
          <nav className="mobile-section-nav" aria-label="Live Monitoring sections">
            <button
              type="button"
              className={activeSection === "dashboard" ? "active" : ""}
              aria-current={activeSection === "dashboard" ? "location" : undefined}
              onClick={() => navigateTo("dashboard")}
            >
              Overview
            </button>
            <button
              type="button"
              className={activeSection === "logs" ? "active" : ""}
              aria-current={activeSection === "logs" ? "location" : undefined}
              onClick={() => navigateTo("logs")}
            >
              Logs
            </button>
            <button
              type="button"
              className={activeSection === "anomalies" ? "active" : ""}
              aria-current={activeSection === "anomalies" ? "location" : undefined}
              onClick={() => navigateTo("anomalies")}
            >
              Anomalies
            </button>
            <button
              type="button"
              className={activeSection === "root-cause" ? "active" : ""}
              aria-current={activeSection === "root-cause" ? "location" : undefined}
              onClick={() => navigateTo("root-cause")}
            >
              Root cause
            </button>
          </nav>
        )}


        {activePage === "live" && (
        <section className="stats">

          <div className="stat-card">
            <div className="stat-icon blue">▣</div>

            <div>
              <p>Total Logs</p>
              <h2>{totalLogs}</h2>
            </div>
          </div>


          <div className="stat-card">
            <div className="stat-icon green">✓</div>

            <div>
              <p>INFO</p>
              <h2>{infoLogs}</h2>
            </div>
          </div>


          <div className="stat-card">
            <div className="stat-icon orange">⚠</div>

            <div>
              <p>WARNING</p>
              <h2>{warningLogs}</h2>
            </div>
          </div>


          <div className="stat-card">
            <div className="stat-icon red">!</div>

            <div>
              <p>ERROR</p>
              <h2>{errorLogs}</h2>
            </div>
          </div>

        </section>
        )}

        {activePage === "upload" && (
          <div className="upload-page">
            <section className="upload-workspace-card" aria-labelledby="upload-title">
              <div className="upload-card-heading">
                <div>
                  <p className="upload-eyebrow">ISOLATED FILE ANALYSIS</p>
                  <h2 id="upload-title">Choose a log file</h2>
                  <p>Review anomalies and incident context without adding file contents to the database.</p>
                </div>
                <span className="upload-limit-badge">2 MiB · 20,000 lines max</span>
              </div>

              <form className="upload-form" onSubmit={analyzeUploadedFile}>
                <div
                  className={`upload-drop-zone${uploadDropActive ? " drag-active" : ""}${uploadState.error ? " has-error" : ""}`}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    uploadDragDepthRef.current += 1;
                    setUploadDropActive(true);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "copy";
                  }}
                  onDragLeave={(event) => {
                    event.preventDefault();
                    uploadDragDepthRef.current = Math.max(0, uploadDragDepthRef.current - 1);
                    if (uploadDragDepthRef.current === 0) {
                      setUploadDropActive(false);
                    }
                  }}
                  onDrop={handleUploadDrop}
                >
                  <span className="upload-file-icon" aria-hidden="true">▤</span>
                  <p className="upload-drop-title">Drop your log file here</p>
                  <p className="upload-drop-copy">or choose a file from your computer</p>
                  <label className="upload-browse-button" htmlFor="upload-file-input">
                    Browse files
                  </label>
                  <input
                    ref={uploadInputRef}
                    id="upload-file-input"
                    className="upload-file-input"
                    type="file"
                    accept=".log,.txt,text/plain"
                    aria-describedby="upload-guidance"
                    onChange={handleUploadFileChange}
                    disabled={uploadState.loading}
                  />
                  <p className="upload-guidance" id="upload-guidance">
                    Supports .log and .txt · UTF-8 · Maximum 2 MiB and 20,000 lines
                  </p>
                </div>

                {uploadState.file && (
                  <div className="upload-selected-file">
                    <div className="upload-selected-file-info">
                      <span className="upload-selected-file-icon" aria-hidden="true">LOG</span>
                      <div>
                        <strong>{uploadState.file.name}</strong>
                        <span>{(uploadState.file.size / 1024).toFixed(1)} KB</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="upload-clear-button"
                      onClick={clearUploadFile}
                      disabled={uploadState.loading}
                    >
                      Remove file
                    </button>
                  </div>
                )}

                {uploadState.error && (
                  <div className="request-state error" role="alert">
                    {uploadState.error}
                  </div>
                )}

                {uploadState.loading && (
                  <div className="upload-progress" role="status" aria-live="polite">
                    <span className="upload-spinner" aria-hidden="true" />
                    <span>Parsing and analyzing {uploadState.file?.name || "file"}...</span>
                  </div>
                )}

                <div className="upload-form-footer">
                  <p>Expected line format: timestamp | service | level | message</p>
                  <button
                    type="submit"
                    className="upload-button"
                    disabled={uploadState.loading || !uploadState.file || Boolean(uploadState.error)}
                  >
                    {uploadState.loading ? "Analyzing..." : "Analyze File"}
                  </button>
                </div>
              </form>
            </section>

            <section className="upload-results-panel" aria-labelledby="upload-results-title" aria-live="polite">
              <div className="upload-results-heading">
                <div>
                  <p className="upload-eyebrow">INVESTIGATION</p>
                  <h2 id="upload-results-title">Analysis results</h2>
                </div>
                {uploadState.result && (
                  <span className="upload-result-filename">{uploadState.result.filename}</span>
                )}
              </div>

              {!uploadState.result ? (
                <div className="upload-results-empty" role="status">
                  <span aria-hidden="true">↳</span>
                  <p>Choose a valid log file and analyze it to see its incident summary and events here.</p>
                </div>
              ) : (
                <div className="upload-results-content">
                  <dl className="upload-metrics">
                    <div className="upload-metric total">
                      <dt>Total Lines</dt>
                      <dd>{uploadState.result.total_lines}</dd>
                    </div>
                    <div className="upload-metric parsed">
                      <dt>Parsed Lines</dt>
                      <dd>{uploadState.result.parsed_logs}</dd>
                    </div>
                    <div className="upload-metric rejected">
                      <dt>Rejected Lines</dt>
                      <dd>{uploadState.result.rejected_count}</dd>
                    </div>
                    <div className="upload-metric anomalies">
                      <dt>Detected Anomalies</dt>
                      <dd>{uploadState.result.detected_anomalies.length}</dd>
                    </div>
                  </dl>

                  <div className="upload-root-layout">
                    <section className="upload-root-cause-card">
                      <div className="upload-root-cause-heading">
                        <p className="upload-eyebrow">PROBABLE ROOT CAUSE</p>
                        <span className={`upload-severity-status ${(uploadState.result.severity || "unknown").toLowerCase()}`}>
                          {uploadState.result.severity || "Severity unavailable"}
                        </span>
                      </div>
                      <h3>
                        {uploadState.result.probable_root_cause?.message || "No probable root cause detected"}
                      </h3>
                      <p className="upload-root-service">
                        {uploadState.result.probable_root_cause?.service || "Service unavailable"}
                      </p>
                      <p className="upload-root-explanation">
                        {uploadState.result.explanation || "Explanation unavailable."}
                      </p>
                      <div className="upload-root-footer">
                        <span>Confidence <strong>Heuristic</strong></span>
                        <strong>
                          {Number.isFinite(uploadState.result.confidence)
                            ? `${(uploadState.result.confidence * 100).toFixed(0)}%`
                            : "Unavailable"}
                        </strong>
                        {(uploadState.result.related_events.length > 0
                          || uploadState.result.probable_root_cause) && (
                          <button
                            type="button"
                            className="investigate-incident-button"
                            onClick={(event) => openIncidentInvestigation(
                              uploadState.result,
                              "upload",
                              uploadState.result.filename,
                              event
                            )}
                          >
                            Investigate incident
                          </button>
                        )}
                      </div>
                    </section>
                    <div className="upload-event-sections">
                      <UploadEventSection
                        title="Detected anomalies"
                        events={uploadState.result.detected_anomalies}
                        emptyMessage="No anomalies were flagged by the current detector."
                        eventKind="anomalies"
                      />
                      <UploadEventSection
                        title="Related incident events"
                        events={uploadState.result.related_events}
                        emptyMessage="No related ERROR or WARNING events were identified."
                        eventKind="related"
                      />
                      <UploadEventSection
                        title="Recovery events"
                        events={uploadState.result.recovery_events}
                        emptyMessage="No recovery events were identified."
                        eventKind="recovery"
                      />
                    </div>
                  </div>

                  {uploadState.result.rejected_lines.length > 0 && (
                    <details className="upload-rejected-details">
                      <summary>Rejected lines ({uploadState.result.rejected_count})</summary>
                      <ol>
                        {uploadState.result.rejected_lines.map((line) => (
                          <li key={line.line_number}>
                            <strong>Line {line.line_number}:</strong> {line.reason}
                            <code>{line.line}{line.truncated ? "..." : ""}</code>
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                </div>
              )}
            </section>
          </div>
        )}

        {activePage === "live" && (
        <>
        <section className="service-health-card">
          <div className="section-title">
            <div>
              <h2>Service Health Overview</h2>
              <p>Rule-based status from all stored logs, not an ML prediction</p>
            </div>
          </div>

          {serviceHealthState.loading && !serviceHealthState.data && (
            <div className="request-state info" role="status">
              Loading service health...
            </div>
          )}

          {serviceHealthState.error && !serviceHealthState.data && (
            <div className="request-state error" role="alert">
              Service health could not be loaded: {serviceHealthState.error}
            </div>
          )}

          {serviceHealthState.error && serviceHealthState.data && (
            <div className="request-state error" role="alert">
              Service health may be stale. Showing the last successful result.
            </div>
          )}

          {serviceHealthState.data?.length === 0 && !serviceHealthState.error && (
            <div className="request-state info" role="status">
              No services are present in the current logs.
            </div>
          )}

          {serviceHealth.length > 0 && (
            <div className="service-health-grid">
              {serviceHealth.map((service) => (
                <article
                  className="service-health-item"
                  key={getServiceKey(service.service)}
                >
                  <div className="service-health-heading">
                    <button
                      type="button"
                      className="service-health-filter"
                      aria-label={`Filter logs for ${service.service || "missing service name"}`}
                      onClick={() => {
                        setServiceFilter(getServiceKey(service.service));
                        navigateTo("logs");
                      }}
                    >
                      {service.service || "Missing service name"}
                    </button>
                    <span
                      className={`service-health-status ${service.health_status.toLowerCase()}`}
                    >
                      {service.health_status}
                    </span>
                  </div>
                  <dl className="service-health-counts">
                    <div>
                      <dt>Total logs</dt>
                      <dd>{service.total_logs}</dd>
                    </div>
                    <div>
                      <dt>ERROR</dt>
                      <dd>{service.error_count}</dd>
                    </div>
                    <div>
                      <dt>WARNING</dt>
                      <dd>{service.warning_count}</dd>
                    </div>
                    <div>
                      <dt>Most recent</dt>
                      <dd>{service.most_recent_timestamp || "Unavailable"}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="analytics-card">
          <div className="section-title">
            <div>
              <h2>Log Analytics &amp; Trends</h2>
              <p>Database log activity and detector results</p>
            </div>
            <label className="trend-range-control">
              <span>Time range</span>
              <select
                aria-label="Trend chart time range"
                value={trendRange}
                onChange={(event) => setTrendRange(event.target.value)}
              >
                <option value="1h">Last hour</option>
                <option value="24h">Last 24 hours</option>
                <option value="all">All available logs</option>
              </select>
            </label>
          </div>

          {analyticsState.loading && !analytics && (
            <div className="request-state info" role="status">
              Loading database analytics...
            </div>
          )}

          {analyticsState.error && !analytics && (
            <div className="request-state error" role="alert">
              Log analytics could not be loaded: {analyticsState.error}
            </div>
          )}

          {analyticsState.error && analytics && (
            <div className="request-state error" role="alert">
              Analytics may be stale. Showing the last successful result.
            </div>
          )}

          {analytics && analytics.total_logs === 0 && !analyticsState.error && (
            <div className="request-state info" role="status">
              No database logs are available for analytics.
            </div>
          )}

          {analytics && analytics.total_logs > 0 && (
            <>
              <p className="analytics-scope">
                Database logs only. Volume interval: {analytics.bucket_interval_label || "unavailable"}.
                {analytics.invalid_timestamp_count > 0 && (
                  <> {analytics.invalid_timestamp_count} log(s) with missing or invalid timestamps are excluded from volume buckets.</>
                )}
              </p>
              <div className="trend-chart-grid">
                <div className="analytics-chart-panel">
                  {trendBuckets.length > 0 ? (
                    <TrendChart
                      title="Log Volume Over Time"
                      buckets={trendBuckets}
                      series={[{ key: "count", color: "#2563eb", label: "Logs" }]}
                    />
                  ) : (
                    <div className="request-state info" role="status">
                      No valid timestamps fall within the selected range.
                    </div>
                  )}
                  <p className="chart-axis-caption">
                    Time axis uses local time · {analytics.bucket_interval_label} buckets
                  </p>
                </div>

                <div className="analytics-chart-panel">
                  <h3>Log Severity Distribution</h3>
                  <SeverityDistributionChart counts={analytics.severity_counts} />
                  <div className="severity-chart-legend" aria-label="Severity color legend">
                    <span><i className="severity-swatch info" />INFO</span>
                    <span><i className="severity-swatch warning" />WARNING</span>
                    <span><i className="severity-swatch error" />ERROR</span>
                    {analytics.severity_counts.UNKNOWN > 0 && (
                      <span><i className="severity-swatch unknown" />UNKNOWN</span>
                    )}
                  </div>
                </div>

                <div className="analytics-chart-panel">
                  <h3>Anomaly Summary</h3>
                  <p className="analytics-chart-caption">
                    Existing detector applied to database log IDs only; uploaded files are excluded.
                  </p>
                  {analysisState.error ? (
                    <div className="request-state error" role="alert">
                      Anomaly totals are unavailable: {analysisState.error}
                    </div>
                  ) : anomalySummary ? (
                    <AnomalySummaryChart summary={anomalySummary} />
                  ) : (
                    <div className="request-state info" role="status">
                      Waiting for anomaly results from the same database snapshot.
                    </div>
                  )}
                  <p className="analytics-chart-caption">
                    Anomalies use the current Isolation Forest and timestamped ERROR-burst rules, not ERROR counts alone.
                  </p>
                </div>
              </div>
            </>
          )}
        </section>


        <section className="analysis-card" ref={analysisSectionRef}>

          <div className="section-title">

            <div>
              <h2>AI Incident Analysis</h2>
              <p>Automated root-cause detection</p>
            </div>

            <div className="analysis-actions">
              {analysis
                && analysis.analyzed_logs.length > 0
                && (analysis.related_events.length > 0 || analysis.probable_root_cause) && (
                <button
                  type="button"
                  className="investigate-incident-button"
                  onClick={(event) => openIncidentInvestigation(
                    analysis,
                    "database",
                    null,
                    event
                  )}
                >
                  Investigate incident
                </button>
              )}
              <span className="ai-badge">AI ANALYSIS</span>
            </div>

          </div>


          {analysisState.loading && !analysis && (
            <div className="request-state info" role="status">
              Loading incident analysis...
            </div>
          )}

          {analysisState.error && (
            <div className="request-state error" role="alert">
              <strong>
                {analysis ? "Could not refresh incident analysis." : "Incident analysis could not be loaded."}
              </strong>{" "}
              {analysisState.error}
              {analysis && (
                <span>
                  {" "}Showing the last successful analysis from{" "}
                  {new Date(analysisState.updatedAt).toLocaleTimeString()}.
                </span>
              )}
            </div>
          )}

          {analysis && !analysisState.error && (
            <p className="last-updated">
              Last successful analysis update:{" "}
              {new Date(analysisState.updatedAt).toLocaleTimeString()}
            </p>
          )}

          {analysis && analysis.analyzed_logs.length === 0 && !analysisState.error && (
            <div className="request-state info" role="status">
              No logs are available for analysis.
            </div>
          )}

          {analysis && analysis.analyzed_logs.length > 0 && (

            <div className="analysis-grid">

              <div className="root-cause">

                <p className="label">
                  PROBABLE ROOT CAUSE
                </p>

                <h2>
                  {analysis.probable_root_cause
                    ? analysis.probable_root_cause.message
                    : "No root cause detected"}
                </h2>

                <p className="service">
                  Service:{" "}
                  {analysis.probable_root_cause
                    ? analysis.probable_root_cause.service
                    : "-"}
                </p>

              </div>


              <div className="metric">

                <p className="label">
                  SEVERITY
                </p>

                <div className="severity-high">
                  {analysis.severity}
                </div>

              </div>


              <div className="metric">

                <p className="label">
                  CONFIDENCE (HEURISTIC)
                </p>

                <div className="confidence">
                  {(analysis.confidence * 100).toFixed(0)}%
                </div>

              </div>

            </div>

          )}


          {analysis && analysis.analyzed_logs.length > 0 && (

            <div className="explanation">

              <div className="explanation-icon">
                ✦
              </div>

              <div>

                <p className="label">
                  AI EXPLANATION
                </p>

                <p>
                  {analysis.explanation}
                </p>

              </div>

            </div>

          )}

        </section>


        <section className="events-card">

          <div className="section-title">

            <div>
              <h2>Related Events</h2>
              <p>Events connected to the detected incident</p>
            </div>

            <span className="event-count">
              {analysis?.related_events?.length || 0} Events
            </span>

          </div>

          {analysisState.loading && !analysis && (
            <div className="request-state info" role="status">
              Loading related events...
            </div>
          )}

          {analysisState.error && (
            <div className="request-state error" role="alert">
              {analysis
                ? `Related events may be stale; last successful analysis was at ${new Date(analysisState.updatedAt).toLocaleTimeString()}.`
                : `Related events could not be loaded: ${analysisState.error}`}
            </div>
          )}

          {analysis && analysis.analyzed_logs.length === 0 && !analysisState.error && (
            <div className="request-state info" role="status">
              No logs are available to correlate.
            </div>
          )}

          {analysis && analysis.analyzed_logs.length > 0 && analysis.related_events.length === 0 && !analysisState.error && (
            <div className="request-state info" role="status">
              No related ERROR or WARNING events were found.
            </div>
          )}

          <div className="event-list">

            {timelineEvents.map((event, index) => {
              const isRootCause = event.id === analysis?.probable_root_cause?.id;
              const levelClass = event.level === "INFO"
                ? "info"
                : event.level === "WARNING"
                ? "warning"
                : event.level === "ERROR"
                ? "error"
                : "";

              return (
              <div
                className={`event${isRootCause ? " event-root-cause" : ""}`}
                key={event.id}
              >

                <div className={`event-number event-marker ${levelClass}`}>
                  {index + 1}
                </div>

                <div className="event-line"></div>

                <div className="event-content">

                  <small className="event-timestamp">
                    {event.timestamp || "Timestamp unavailable"}
                  </small>

                  <div className="event-top">

                    <strong>
                      {event.service}
                    </strong>

                    <span className={`level ${levelClass}`}>
                      {event.level}
                    </span>

                    {isRootCause && (
                      <span className="root-cause-badge">
                        Probable root cause
                      </span>
                    )}

                  </div>

                  <p>
                    {event.message}
                  </p>

                </div>

              </div>

              );
            })}

          </div>

        </section>

        <section className="impact-card">
          <div className="section-title">
            <div>
              <h2>Incident Impact</h2>
              <p>Summary and suggested investigation steps from related events</p>
            </div>
          </div>

          {analysisState.loading && !analysis && (
            <div className="request-state info" role="status">
              Loading incident impact...
            </div>
          )}

          {analysisState.error && !analysis && (
            <div className="request-state error" role="alert">
              Incident impact is unavailable: {analysisState.error}
            </div>
          )}

          {analysis && !hasIncidentData && (
            <div className="request-state info" role="status">
              No incident data is currently available to summarize.
            </div>
          )}

          {analysis && hasIncidentData && (
            <>
              <div className="impact-metrics">
                <div className="impact-metric">
                  <span>Related Events</span>
                  <strong>{relatedEvents.length}</strong>
                </div>
                <div className="impact-metric">
                  <span>Affected Services</span>
                  <strong>{affectedServices.length}</strong>
                </div>
                <div className="impact-metric error">
                  <span>ERROR</span>
                  <strong>{relatedErrorCount}</strong>
                </div>
                <div className="impact-metric warning">
                  <span>WARNING</span>
                  <strong>{relatedWarningCount}</strong>
                </div>
              </div>

              {impactRecommendations.length > 0 && (
                <div className="impact-recommendations">
                  <h3>Troubleshooting recommendations</h3>
                  <ul>
                    {impactRecommendations.map((recommendation) => (
                      <li key={recommendation}>{recommendation}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </section>


        <section className="logs-card" ref={logsSectionRef}>

          <div className="section-title">

            <div>
              <h2>{activeSection === "anomalies" ? "Detected Anomalies" : "Recent Logs"}</h2>
              <p>
                {activeSection === "anomalies"
                  ? "Logs flagged by the existing anomaly analysis"
                  : "Latest application events"}
              </p>
            </div>

            <span className="live-badge">
              ● LIVE
            </span>

          </div>

          <div className="logs-controls">
            <input
              type="search"
              aria-label="Search logs by message or service"
              placeholder="Search message or service..."
              value={logSearch}
              onChange={(event) => setLogSearch(event.target.value)}
            />

            <select
              aria-label="Filter logs by service"
              value={serviceFilter}
              onChange={(event) => setServiceFilter(event.target.value)}
            >
              <option value="ALL">All services</option>
              {serviceHealth.map((service) => (
                <option
                  key={getServiceKey(service.service)}
                  value={getServiceKey(service.service)}
                >
                  {service.service || "Missing service name"}
                </option>
              ))}
            </select>

            <select
              aria-label="Filter logs by severity"
              value={severityFilter}
              onChange={(event) => setSeverityFilter(event.target.value)}
            >
              <option value="ALL">All severities</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>

            <button
              type="button"
              className="clear-filters"
              onClick={() => {
                setLogSearch("");
                setSeverityFilter("ALL");
                setServiceFilter("ALL");
              }}
              disabled={
                logSearch === ""
                && severityFilter === "ALL"
                && serviceFilter === "ALL"
              }
            >
              Clear filters
            </button>

            <button
              type="button"
              className="export-csv"
              onClick={exportVisibleLogs}
              disabled={visibleLogs.length === 0}
            >
              Export CSV
            </button>
          </div>

          {logsState.data && visibleLogs.length === 0 && (
            <p className="export-empty" role="status">
              No logs to export.
            </p>
          )}

          {logsState.loading && !logsState.data && (
            <div className="request-state info" role="status">
              Loading logs...
            </div>
          )}

          {logsState.error && (
            <div className="request-state error" role="alert">
              <strong>
                {logsState.data ? "Could not refresh logs." : "Logs could not be loaded."}
              </strong>{" "}
              {logsState.error}
              {logsState.data && (
                <span>
                  {" "}Showing the last successful data from{" "}
                  {new Date(logsState.updatedAt).toLocaleTimeString()}.
                </span>
              )}
            </div>
          )}

          {logsState.data?.length > 0 && !logsState.error && (
            <p className="last-updated">
              Last successful log update:{" "}
              {new Date(logsState.updatedAt).toLocaleTimeString()}
            </p>
          )}

          {logsState.data?.length === 0 && !logsState.error && (
            <div className="request-state info" role="status">
              No logs are available.
            </div>
          )}


          {logsState.data?.length > 0 && activeSection === "anomalies" && !analysis && (
            <div
              className={`request-state ${analysisState.error ? "error" : "info"}`}
              role={analysisState.error ? "alert" : "status"}
            >
              {analysisState.error
                ? `Anomaly analysis is unavailable: ${analysisState.error}`
                : "Loading anomaly analysis..."}
            </div>
          )}

          {logsState.data?.length > 0 && activeSection === "anomalies" && analysis && visibleLogs.length === 0 && (
            <div className="request-state info" role="status">
              {analyzedLogs.some((log) => log.anomaly)
                ? "No anomalous logs match the current search and severity filters."
                : "No logs are currently flagged as anomalous."}
            </div>
          )}

          {logsState.data?.length > 0 && activeSection !== "anomalies" && filteredLogs.length === 0 && (
            <div className="request-state info" role="status">
              No logs match the selected search and severity filters.
            </div>
          )}

          {logsState.data?.length > 0 && visibleLogs.length > 0 && (
          <div className="table-container">

            <table>

              <thead>

                <tr>
                  <th>ID</th>
                  <th>TIME</th>
                  <th>SERVICE</th>
                  <th>LEVEL</th>
                  <th>ANOMALY</th>
                  <th>MESSAGE</th>
                  <th>ACTION</th>
                </tr>

              </thead>


              <tbody>

                {[...visibleLogs].reverse().map((log) => (

                  <tr key={log.id}>

                    <td className="id-cell">
                      #{log.id}
                    </td>

                    <td>
                      {log.timestamp}
                    </td>

                    <td>

                      <span className="service-name">
                        {log.service}
                      </span>

                    </td>

                    <td>

                      <span
                        className={
                          log.level === "ERROR"
                            ? "level error"
                            : log.level === "WARNING"
                            ? "level warning"
                            : "level info"
                        }
                      >
                        {log.level}
                      </span>

                    </td>

                    <td>

                      {analysis ? (log.anomaly ? (

                        <span className="anomaly-badge">
                          🔴 Anomaly
                        </span>

                      ) : (

                        <span className="normal-badge">
                          ✓ Normal
                        </span>

                      )) : (
                        <span className="analysis-unavailable">
                          Unavailable
                        </span>
                      )}

                    </td>

                    <td className="message">
                      {log.message}
                    </td>

                    <td>
                      <button
                        type="button"
                        className="log-details-button"
                        aria-label={`View details for log ${log.id}`}
                        onClick={(event) => openLogDetails(log, event)}
                      >
                        Details
                      </button>
                    </td>

                  </tr>

                ))}

              </tbody>

            </table>

          </div>
          )}

        </section>

        </>
        )}


        <footer>
          AI Log Analyzer • Real-Time Monitoring System
        </footer>

        {selectedIncident && (
          <div
            className="log-detail-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                closeIncidentInvestigation();
              }
            }}
          >
            <section
              className="log-detail-dialog incident-investigation-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="incident-detail-title"
              onKeyDown={handleIncidentDialogKeyDown}
            >
              <div className="log-detail-heading">
                <div className="incident-dialog-title">
                  <p className="label">INCIDENT INVESTIGATION</p>
                  <h2 id="incident-detail-title">{selectedIncident.title}</h2>
                  <p>{selectedIncident.source}</p>
                </div>
                <button
                  ref={incidentCloseButtonRef}
                  type="button"
                  className="log-detail-close"
                  aria-label="Close incident details"
                  onClick={closeIncidentInvestigation}
                >
                  Close
                </button>
              </div>

              <dl className="incident-summary-metrics">
                <div>
                  <dt>Severity</dt>
                  <dd>
                    <span className={`incident-severity ${selectedIncident.severity?.toLowerCase() || "unknown"}`}>
                      {selectedIncident.severity || "Unavailable"}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Confidence (heuristic)</dt>
                  <dd>
                    {selectedIncident.confidence === null
                      ? "Unavailable"
                      : `${(selectedIncident.confidence * 100).toFixed(0)}%`}
                  </dd>
                </div>
                <div>
                  <dt>Incident start</dt>
                  <dd>
                    {selectedIncident.startTimestamp || "Unavailable"}
                  </dd>
                </div>
                <div>
                  <dt>Incident end</dt>
                  <dd>
                    {selectedIncident.endTimestamp || "Unavailable"}
                  </dd>
                </div>
              </dl>

              <section className="incident-investigation-section">
                <h3>Probable root-cause candidate</h3>
                {selectedIncident.rootCause ? (
                  <div className="incident-root-cause">
                    <strong>
                      {selectedIncident.rootCause.service || "Service unavailable"}
                    </strong>
                    <p>{selectedIncident.rootCause.message || "Message unavailable"}</p>
                    <span>Inferred from the existing service-priority and timestamp heuristics.</span>
                  </div>
                ) : (
                  <div className="request-state info" role="status">
                    No probable root cause is available for this analysis.
                  </div>
                )}
                <p className="incident-explanation">
                  {selectedIncident.explanation || "Explanation unavailable."}
                </p>
              </section>

              <section className="incident-investigation-section">
                <h3>Observed event timeline</h3>
                {selectedIncident.timeline.length === 0 ? (
                  <div className="request-state info" role="status">
                    No related incident events are available.
                  </div>
                ) : (
                  <ol className="incident-timeline">
                    {selectedIncident.timeline.map((event) => {
                      const levelClass = event.level === "INFO"
                        ? "info"
                        : event.level === "WARNING"
                        ? "warning"
                        : event.level === "ERROR"
                        ? "error"
                        : "";
                      return (
                        <li className="incident-timeline-event" key={event.key}>
                          <span className={`incident-timeline-marker ${levelClass}`} />
                          <div className="incident-timeline-content">
                            <div className="incident-timeline-heading">
                              <time>
                                {event.timestampAvailable
                                  ? event.timestamp
                                  : "Timestamp unavailable"}
                              </time>
                              <span className="level-chip">
                                {event.level || "Level unavailable"}
                              </span>
                              {event.kind === "recovery" && (
                                <span className="incident-event-tag recovery-tag">Recovery</span>
                              )}
                              {event.anomaly && (
                                <span className="incident-event-tag anomaly-tag">Detected anomaly</span>
                              )}
                              {event.isProbableRootCause && (
                                <span className="incident-event-tag root-tag">Probable root-cause candidate</span>
                              )}
                            </div>
                            <strong>{event.service || "Service unavailable"}</strong>
                            <p>{event.message || "Message unavailable"}</p>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </section>

              <div className="incident-investigation-columns">
                <section className="incident-investigation-section">
                  <h3>Detected anomalies ({selectedIncident.anomalies.length})</h3>
                  {selectedIncident.anomalies.length > 0 ? (
                    <ul className="incident-observation-list">
                      {selectedIncident.anomalies.map((event) => (
                        <li key={event.key}>
                          {event.timestamp || "Timestamp unavailable"} · {event.service || "Service unavailable"}
                          <p>{event.message || "Message unavailable"}</p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="incident-muted">No detected anomalies are associated with these events.</p>
                  )}
                </section>

                <section className="incident-investigation-section">
                  <h3>Recovery events ({selectedIncident.recoveryEvents.length})</h3>
                  {selectedIncident.recoveryEvents.length > 0 ? (
                    <ul className="incident-observation-list">
                      {selectedIncident.recoveryEvents.map((event) => (
                        <li key={event.key}>
                          {event.timestamp || "Timestamp unavailable"} · {event.service || "Service unavailable"}
                          <p>{event.message || "Message unavailable"}</p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="incident-muted">No recovery events were identified.</p>
                  )}
                </section>

                <section className="incident-investigation-section">
                  <h3>Affected services ({selectedIncident.affectedServices.length})</h3>
                  {selectedIncident.affectedServices.length > 0 ? (
                    <ul className="incident-service-list">
                      {selectedIncident.affectedServices.map((service) => (
                        <li key={service}>{service}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="incident-muted">Affected services unavailable.</p>
                  )}
                </section>
              </div>

              <p className="incident-causality-note">
                Events shown above are observed logs. Root-cause selection and temporal correlation are heuristic and do not prove causation.
              </p>
            </section>
          </div>
        )}

        {selectedLog && (
          <div
            className="log-detail-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                closeLogDetails();
              }
            }}
          >
            <section
              className="log-detail-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="log-detail-title"
              onKeyDown={handleLogDetailsKeyDown}
            >
              <div className="log-detail-heading">
                <div>
                  <p className="label">LOG DETAILS</p>
                  <h2 id="log-detail-title">Log #{selectedLog.id}</h2>
                </div>
                <button
                  ref={detailCloseButtonRef}
                  type="button"
                  className="log-detail-close"
                  aria-label="Close log details"
                  onClick={closeLogDetails}
                >
                  Close
                </button>
              </div>

              <dl className="log-detail-list">
                <div>
                  <dt>Timestamp</dt>
                  <dd>{selectedLog.timestamp}</dd>
                </div>
                <div>
                  <dt>Service</dt>
                  <dd>{selectedLog.service}</dd>
                </div>
                <div>
                  <dt>Severity</dt>
                  <dd>
                    <span
                      className={
                        selectedLog.level === "ERROR"
                          ? "level error"
                          : selectedLog.level === "WARNING"
                          ? "level warning"
                          : "level info"
                      }
                    >
                      {selectedLog.level}
                    </span>
                  </dd>
                </div>
                {typeof selectedLog.anomaly === "boolean" && (
                  <div>
                    <dt>Anomaly status</dt>
                    <dd>
                      <span
                        className={
                          selectedLog.anomaly ? "anomaly-badge" : "normal-badge"
                        }
                      >
                        {selectedLog.anomaly ? "Anomaly" : "Normal"}
                      </span>
                    </dd>
                  </div>
                )}
                <div className="log-detail-message">
                  <dt>Message</dt>
                  <dd>{selectedLog.message}</dd>
                </div>
              </dl>
            </section>
          </div>
        )}

      </main>

    </div>
  );
}

export default App;