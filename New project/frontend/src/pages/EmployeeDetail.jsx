import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { getUser, listTimeEntries, listScreenshots } from "../api";

function localDay(dateStr) {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function todayStr() {
  return localDay(new Date().toISOString());
}
function formatHM(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}
function liveDuration(entry) {
  if (entry.status === "active") {
    return Math.max(0, Math.floor((Date.now() - new Date(entry.start_time).getTime()) / 1000));
  }
  return entry.duration_seconds || 0;
}
function effectiveEnd(entry) {
  return entry.status === "active" ? new Date() : new Date(entry.end_time || entry.start_time);
}
// how many seconds of this entry fall inside [rangeStart, rangeEnd)
function overlapSeconds(entry, rangeStart, rangeEnd) {
  const s = new Date(entry.start_time).getTime();
  const e = effectiveEnd(entry).getTime();
  const start = Math.max(s, rangeStart.getTime());
  const end = Math.min(e, rangeEnd.getTime());
  return Math.max(0, Math.floor((end - start) / 1000));
}
function startOfWeek(date) {
  const d = new Date(date);
  const day = (d.getDay() + 6) % 7; // Monday = 0
  d.setDate(d.getDate() - day);
  d.setHours(0, 0, 0, 0);
  return d;
}
function startOfMonth(date) {
  const d = new Date(date);
  d.setDate(1);
  d.setHours(0, 0, 0, 0);
  return d;
}
function daysInMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
}
function formatTimeRange(entry) {
  const start = new Date(entry.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const end = entry.status === "active"
    ? "now"
    : new Date(entry.end_time || entry.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${start} - ${end}`;
}

export default function EmployeeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const userId = Number(id);

  const [user, setUser] = useState(null);
  const [entries, setEntries] = useState([]);
  const [screenshots, setScreenshots] = useState([]);
  const [dateFilter, setDateFilter] = useState(todayStr());
  const [granularity, setGranularity] = useState("daily"); // daily | weekly | monthly
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([getUser(userId), listTimeEntries(userId), listScreenshots(userId)])
      .then(([u, e, s]) => {
        setUser(u);
        setEntries(e);
        setScreenshots(s);
      })
      .finally(() => setLoading(false));
  }, [userId]);

  const dayEntries = useMemo(
    () => entries.filter((e) => localDay(e.start_time) === dateFilter).sort((a, b) => new Date(a.start_time) - new Date(b.start_time)),
    [entries, dateFilter]
  );
  const dayShots = useMemo(() => screenshots.filter((s) => localDay(s.captured_at) === dateFilter), [screenshots, dateFilter]);

  const activeEntry = entries.find((e) => e.status === "active");
  const workSeconds = dayEntries.reduce((sum, e) => sum + liveDuration(e), 0);

  // Idle Time = gaps between the first "start" and last "end" (or now) where the tracker wasn't running
  const idleSeconds = useMemo(() => {
    if (dayEntries.length === 0) return 0;
    const firstStart = new Date(dayEntries[0].start_time).getTime();
    const lastEntry = dayEntries[dayEntries.length - 1];
    const lastEnd = effectiveEnd(lastEntry).getTime();
    const totalSpan = Math.max(0, Math.floor((lastEnd - firstStart) / 1000));
    return Math.max(totalSpan - workSeconds, 0);
  }, [dayEntries, workSeconds]);

  const avgActivity = dayShots.length
    ? Math.round(dayShots.reduce((sum, s) => sum + (s.activity_level || 0), 0) / dayShots.length)
    : 0;

  // ---- Idle Time chart: derived from tracked activity in each time bucket ----
  const buckets = useMemo(() => {
    const anchor = new Date(`${dateFilter}T00:00:00`);
    const now = new Date();
    const isToday = dateFilter === todayStr();
    const currentHour = isToday ? now.getHours() : 23;

    const buildBucket = (rangeStart, rangeEnd, label) => {
      const effectiveEnd = isToday && rangeEnd.getTime() > now.getTime() ? now : rangeEnd;
      const activeSeconds = entries.reduce((sum, e) => sum + overlapSeconds(e, rangeStart, effectiveEnd), 0);
      const bucketSeconds = Math.max(0, Math.floor((effectiveEnd.getTime() - rangeStart.getTime()) / 1000));
      return { label, seconds: Math.max(0, bucketSeconds - activeSeconds) };
    };

    if (granularity === "daily") {
      const bucketCount = isToday ? currentHour + 1 : 24;
      return Array.from({ length: bucketCount }, (_, h) => {
        const rangeStart = new Date(anchor); rangeStart.setHours(h, 0, 0, 0);
        const rangeEnd = new Date(anchor); rangeEnd.setHours(h + 1, 0, 0, 0);
        return buildBucket(rangeStart, rangeEnd, `${String(h).padStart(2, "0")}:00`);
      });
    }

    if (granularity === "weekly") {
      const weekStart = startOfWeek(anchor);
      return Array.from({ length: 7 }, (_, i) => {
        const rangeStart = new Date(weekStart); rangeStart.setDate(weekStart.getDate() + i);
        const rangeEnd = new Date(rangeStart); rangeEnd.setDate(rangeStart.getDate() + 1);
        return buildBucket(rangeStart, rangeEnd, rangeStart.toLocaleDateString([], { weekday: "short" }));
      });
    }

    const monthStart = startOfMonth(anchor);
    const total = daysInMonth(anchor);
    return Array.from({ length: total }, (_, i) => {
      const rangeStart = new Date(monthStart); rangeStart.setDate(i + 1);
      const rangeEnd = new Date(rangeStart); rangeEnd.setDate(rangeStart.getDate() + 1);
      return buildBucket(rangeStart, rangeEnd, String(i + 1));
    });
  }, [entries, dateFilter, granularity]);

  const maxBucketSeconds = Math.max(...buckets.map((b) => b.seconds), 60);

  const sessionDateLabel = new Date(`${dateFilter}T00:00:00`).toLocaleDateString([], {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  const liveStatus = activeEntry ? (activeEntry.is_idle ? "idle" : "active") : "offline";
  const liveStatusLabel = liveStatus === "active" ? "Live Syncing" : liveStatus === "idle" ? "Idle" : "Offline";

  if (loading) return <div className="loading-state">Loading...</div>;
  if (!user) return <div className="loading-state">Employee not found.</div>;

  return (
    <div>
      <div className="page-header-bar">
        <nav className="page-breadcrumb" aria-label="Breadcrumb">
          <Link to="/" className="breadcrumb-link">
            Dashboard
          </Link>
          <span className="breadcrumb-separator">›</span>
          <span className="breadcrumb-current">EmployeeDetail</span>
        </nav>
        <span className={`pill pill-${liveStatus}`}>
          <span className="pill-dot" /> {liveStatusLabel}
        </span>
      </div>

      <h1>Employee Analytics: {user.name}</h1>
      <p className="subtitle">Detailed tracking and performance metrics for {dateFilter === todayStr() ? "today" : sessionDateLabel}.</p>

      <div className="detail-grid">
        <div className="card profile-card">
          <div className="avatar-circle">{user.name.charAt(0).toUpperCase()}</div>
          <h3>{user.name}</h3>
          <p className="muted">{user.role === "admin" ? "Administrator" : "Employee"}</p>
          <div className="profile-row"><span>Email</span><span>{user.email}</span></div>
          <div className="profile-row">
            <span>Status</span>
            <span className={`pill pill-${liveStatus}`}>
              <span className="pill-dot" /> {liveStatus === "active" ? "Active" : liveStatus === "idle" ? "Idle" : "Offline"}
            </span>
          </div>
          <div className="profile-row"><span>Current Session IP</span><span className="mono">{activeEntry?.start_ip_address || "-"}</span></div>
        </div>

        <div className="metric-cards">
          <div className="metric-card">
            <div className="metric-card-top">
              <span className="stat-label">Work Time</span>
              <span className="metric-icon metric-icon-blue">🕐</span>
            </div>
            <div className="stat-value">{formatHM(workSeconds)}</div>
          </div>
          <div className="metric-card">
            <div className="metric-card-top">
              <span className="stat-label">Idle Time</span>
              <span className="metric-icon metric-icon-amber">⏱</span>
            </div>
            <div className="stat-value">{formatHM(idleSeconds)}</div>
          </div>
          <div className="metric-card">
            <div className="metric-card-top">
              <span className="stat-label">Avg Activity</span>
              <span className="metric-icon metric-icon-purple">📈</span>
            </div>
            <div className="stat-value">{avgActivity}%</div>
          </div>
          <div className="metric-card">
            <div className="metric-card-top">
              <span className="stat-label">Sessions</span>
              <span className="metric-icon metric-icon-purple">🗂</span>
            </div>
            <div className="stat-value">{dayEntries.length}</div>
          </div>
          <button
            type="button"
            className="metric-card metric-card-btn"
            onClick={() => navigate(`/employee/${userId}/screenshots`)}
            title="View all screenshots for this employee"
          >
            <div className="metric-card-top">
              <span className="stat-label">Screenshots</span>
              <span className="metric-icon metric-icon-teal">🖼</span>
            </div>
            <div className="stat-value">{dayShots.length}</div>
            <div className="metric-card-hint">View all →</div>
          </button>
        </div>
      </div>

      <div className="detail-grid-2">
        <div className="card">
          <div className="card-header-row">
            <h3>Idle Time</h3>
            <div className="chart-toolbar">
              <select value={granularity} onChange={(e) => setGranularity(e.target.value)}>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
              <input type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} />
            </div>
          </div>
          <div className="activity-chart-scroll">
            <div className="activity-chart-inner" style={{ minWidth: `${buckets.length * 34}px` }}>
              <div className="chart-plot">
                <div className="chart-gridline" style={{ bottom: "25%" }} />
                <div className="chart-gridline" style={{ bottom: "50%" }} />
                <div className="chart-gridline" style={{ bottom: "75%" }} />
                <div className="chart-bars">
                  {buckets.map((b) => (
                    <div key={b.label} className="activity-bar-col">
                      {b.seconds > 0 ? (
                        <div
                          className="activity-bar"
                          style={{ height: `${Math.max((b.seconds / maxBucketSeconds) * 100, 6)}%` }}
                        >
                          <span className="activity-bar-tip">{formatHM(b.seconds)}</span>
                        </div>
                      ) : (
                        <div className="activity-bar-zero" title="No activity" />
                      )}
                    </div>
                  ))}
                </div>
              </div>
              <div className="chart-labels">
                {buckets.map((b) => (
                  <div key={b.label} className="chart-label-col">{b.label}</div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="card session-card">
          <div className="session-panel-header">
            <span className="session-cal-icon">📅</span>
            <h3>{sessionDateLabel}</h3>
          </div>
          <div className="session-list">
            {dayEntries.map((e, i) => (
              <div key={e.id} className="session-item">
                <div className="session-label">SESSION {i + 1}</div>
                <div className="session-time">🕐 {formatTimeRange(e)}</div>
              </div>
            ))}
            {dayEntries.length === 0 && <p className="muted">No sessions recorded for this day.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}