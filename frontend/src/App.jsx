import { useEffect, useState } from "react";
import "./App.css";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function App() {
  const [logs, setLogs] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [backendStatus, setBackendStatus] = useState("checking");

  useEffect(() => {
    let isActive = true;

    const fetchData = async () => {
      const [logsResult, analysisResult] = await Promise.allSettled([
        fetch(`${API_BASE_URL}/logs`),
        fetch(`${API_BASE_URL}/logs/analyze`)
      ]);

      if (!isActive) {
        return;
      }

      const backendIsReachable = [logsResult, analysisResult].some(
        (result) => result.status === "fulfilled"
      );
      setBackendStatus(backendIsReachable ? "online" : "offline");

      if (logsResult.status === "fulfilled") {
        logsResult.value.json()
          .then((data) => {
            if (isActive) setLogs(data);
          })
          .catch((error) => console.error("Log Error:", error));
      } else {
        console.error("Log Error:", logsResult.reason);
      }

      if (analysisResult.status === "fulfilled") {
        analysisResult.value.json()
          .then((data) => {
            if (isActive) setAnalysis(data);
          })
          .catch((error) => console.error("Analysis Error:", error));
      } else {
        console.error("Analysis Error:", analysisResult.reason);
      }
    };

    fetchData();

    const interval = setInterval(fetchData, 2000);

    return () => {
      isActive = false;
      clearInterval(interval);
    };
  }, []);

  const analyzedLogs = analysis?.analyzed_logs || logs;

  const totalLogs = logs.length;
  const infoLogs = logs.filter((log) => log.level === "INFO").length;
  const warningLogs = logs.filter((log) => log.level === "WARNING").length;
  const errorLogs = logs.filter((log) => log.level === "ERROR").length;
  const anomalyLogs = analyzedLogs.filter((log) => log.anomaly).length;

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

        <div className="menu active">
          <span>▣</span>
          Dashboard
        </div>

        <div className="menu">
          <span>◉</span>
          Log Monitoring
        </div>

        <div className="menu">
          <span>⚠</span>
          Anomalies
        </div>

        <div className="menu">
          <span>⌁</span>
          Root Cause
        </div>

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
            <h1>System Dashboard</h1>
            <p>Real-time log monitoring and AI-powered analysis</p>
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


        <section className="analysis-card">

          <div className="section-title">

            <div>
              <h2>AI Incident Analysis</h2>
              <p>Automated root-cause detection</p>
            </div>

            <span className="ai-badge">
              AI ANALYSIS
            </span>

          </div>


          {analysis && (

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
                  CONFIDENCE
                </p>

                <div className="confidence">
                  {(analysis.confidence * 100).toFixed(0)}%
                </div>

              </div>

            </div>

          )}


          {analysis && (

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


          <div className="event-list">

            {analysis?.related_events?.map((event, index) => (

              <div className="event" key={event.id}>

                <div className="event-number">
                  {index + 1}
                </div>

                <div className="event-line"></div>

                <div className="event-content">

                  <div className="event-top">

                    <strong>
                      {event.service}
                    </strong>

                    <span className="error-badge">
                      {event.level}
                    </span>

                  </div>

                  <p>
                    {event.message}
                  </p>

                  <small>
                    {event.timestamp}
                  </small>

                </div>

              </div>

            ))}

          </div>

        </section>


        <section className="logs-card">

          <div className="section-title">

            <div>
              <h2>Recent Logs</h2>
              <p>Latest application events</p>
            </div>

            <span className="live-badge">
              ● LIVE
            </span>

          </div>


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
                </tr>

              </thead>


              <tbody>

                {[...analyzedLogs].reverse().map((log) => (

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

                      {log.anomaly ? (

                        <span className="anomaly-badge">
                          🔴 Anomaly
                        </span>

                      ) : (

                        <span className="normal-badge">
                          ✓ Normal
                        </span>

                      )}

                    </td>

                    <td className="message">
                      {log.message}
                    </td>

                  </tr>

                ))}

              </tbody>

            </table>

          </div>

        </section>


        <footer>
          AI Log Analyzer • Real-Time Monitoring System
        </footer>

      </main>

    </div>
  );
}

export default App;