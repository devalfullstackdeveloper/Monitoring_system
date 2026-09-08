import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listUsers, listTimeEntries, listScreenshots, createUser } from "../api";

function formatClock(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatHM(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

// active entries never get duration_seconds updated until /stop is called,
// so compute the live elapsed time for whichever entry is still running
function liveDuration(entry) {
  if (entry.status === "active") {
    return Math.max(0, Math.floor((Date.now() - new Date(entry.start_time).getTime()) / 1000));
  }
  return entry.duration_seconds || 0;
}

function timeAgo(dateStr) {
  if (!dateStr) return "-";
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} mins ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs > 1 ? "s" : ""} ago`;
  const days = Math.floor(hrs / 24);
  return days === 1 ? "Yesterday" : `${days} days ago`;
}

function localDay(dateStr) {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function todayStr() {
  return localDay(new Date().toISOString());
}

export default function Dashboard() {
  const navigate = useNavigate();

  const [users, setUsers] = useState([]);
  const [entries, setEntries] = useState([]);
  const [screenshots, setScreenshots] = useState([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState(todayStr());

  const [showAddModal, setShowAddModal] = useState(false);
  const [newMember, setNewMember] = useState({ name: "", email: "", password: "", role: "employee" });
  const [addError, setAddError] = useState("");
  const [saving, setSaving] = useState(false);

  async function loadAll() {
    setLoading(true);
    const u = await listUsers();
    setUsers(u);
    const [e, s] = await Promise.all([listTimeEntries(), listScreenshots()]);
    setEntries(e);
    setScreenshots(s);
    setLoading(false);
  }

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 30000); // keep live times fresh
    return () => clearInterval(interval);
  }, []);

  const rows = useMemo(() => {
    return users.map((u) => {
      const userEntries = entries.filter((e) => e.user_id === u.id);
      const activeEntry = userEntries.find((e) => e.status === "active");
      const entriesToday = userEntries.filter((e) => localDay(e.start_time) === dateFilter);
      const secondsToday = entriesToday.reduce((sum, e) => sum + liveDuration(e), 0);

      const userShots = screenshots
        .filter((s) => s.user_id === u.id)
        .sort((a, b) => new Date(b.captured_at) - new Date(a.captured_at));
      const lastShot = userShots[0];
      const lastActiveAt = activeEntry?.last_seen_at || lastShot?.captured_at || activeEntry?.start_time || userEntries[0]?.start_time;

      let status = "offline";
      if (activeEntry) {
        status = activeEntry.is_idle ? "idle" : "active";
      }

      return { user: u, status, currentIp: activeEntry?.start_ip_address || "-", secondsToday, lastActiveAt };
    });
  }, [users, entries, screenshots, dateFilter]);

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      const q = search.toLowerCase();
      const matchesSearch = r.user.name.toLowerCase().includes(q) || r.user.email.toLowerCase().includes(q);
      const matchesStatus = statusFilter === "all" || r.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [rows, search, statusFilter]);

  const stats = useMemo(() => ({
    total: users.length,
    activeNow: rows.filter((r) => r.status === "active").length,
    idleNow: rows.filter((r) => r.status === "idle").length,
    offlineNow: rows.filter((r) => r.status === "offline").length,
    totalSeconds: rows.reduce((sum, r) => sum + r.secondsToday, 0),
  }), [rows, users]);

  const trackerRunning = stats.activeNow + stats.idleNow > 0;

  async function handleAddMember(e) {
    e.preventDefault();
    setAddError("");
    setSaving(true);
    try {
      await createUser(newMember);
      setShowAddModal(false);
      setNewMember({ name: "", email: "", password: "", role: "employee" });
      await loadAll();
    } catch (err) {
      setAddError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="dashboard-header">
        <div className="search-wrap">
          <span className="search-icon">⌕</span>
          <input
            className="search-input"
            placeholder="Search members or IP..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="header-actions">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
            <option value="all">All Statuses</option>
            <option value="active">Active</option>
            <option value="idle">Idle</option>
            <option value="offline">Offline</option>
          </select>
          <input className="header-date" type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} aria-label="Filter by date" />
          <button className="btn-primary" onClick={() => setShowAddModal(true)}>＋ Add Member</button>
        </div>
      </div>

      <div className="page-title-row">
        <div>
          <h1>Team Overview</h1>
          <p className="subtitle">Monitor real-time employee activity and status.</p>
        </div>
        <div className={`updated-indicator ${trackerRunning ? "tracker-running" : "tracker-stopped"}`}>
          <span /> Tracker {trackerRunning ? "Running" : "Stopped"}
        </div>
      </div>

      <div className="stat-cards">
        <div className="stat-card">
          <div className="stat-label">Total Employees</div>
          <div className="stat-value">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Active Now</div>
          <div className="stat-value stat-active">● {stats.activeNow}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Currently Idle</div>
          <div className="stat-value stat-idle">● {stats.idleNow}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Offline</div>
          <div className="stat-value stat-offline">● {stats.offlineNow}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Work Hours Today</div>
          <div className="stat-value">{formatHM(stats.totalSeconds)}</div>
        </div>
      </div>

      <div className="table-card">
        <div className="table-heading">
          <div><h2>Member Activity</h2><span>{users.length} members registered</span></div>
          <div className="table-tabs"><button className={statusFilter === "all" ? "selected" : ""} onClick={() => setStatusFilter("all")}>All ({users.length})</button><button className={statusFilter === "active" ? "selected" : ""} onClick={() => setStatusFilter("active")}>Active ({stats.activeNow})</button><button className={statusFilter === "offline" ? "selected" : ""} onClick={() => setStatusFilter("offline")}>Offline ({stats.offlineNow})</button></div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Employee</th>
              <th>Email</th>
              <th>Status</th>
              <th>Current Session IP</th>
              <th>Today's Time</th>
              <th>Last Active</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((r) => (
              <tr key={r.user.id}>
                <td>
                  <div className="name-cell">
                    <span className={`avatar-sm avatar-${r.status}`}>{r.user.name.charAt(0).toUpperCase()}</span>
                    <div><strong>{r.user.name}</strong><small>{r.user.role === "admin" ? "Team Admin" : "Member"}</small></div>
                  </div>
                </td>
                <td>{r.user.email}</td>
                <td>
                  <span className={`pill pill-${r.status}`}>
                    <span className="pill-dot" /> {r.status.charAt(0).toUpperCase() + r.status.slice(1)}
                  </span>
                </td>
                <td className="mono">{r.currentIp}</td>
                <td className="mono">{formatClock(r.secondsToday)}</td>
                <td>{timeAgo(r.lastActiveAt)}</td>
                <td>
                  <button className="btn-view" onClick={() => navigate(`/employee/${r.user.id}`)}>View</button>
                </td>
              </tr>
            ))}
            {!loading && filteredRows.length === 0 && (
              <tr><td colSpan={7} className="empty-state">No employees match your filters.</td></tr>
            )}
          </tbody>
        </table>
        <div className="table-footer"><span>Showing 1 to {filteredRows.length} of {users.length} members</span><div className="pagination"><button disabled>Previous</button><button className="page-current">1</button><button disabled>Next</button></div></div>
      </div>

      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <h3>Add Member</h3>
            {addError && <div className="alert-error">{addError}</div>}
            <form onSubmit={handleAddMember}>
              <label>Name</label>
              <input required value={newMember.name} onChange={(e) => setNewMember({ ...newMember, name: e.target.value })} />
              <label>Email</label>
              <input required type="email" value={newMember.email} onChange={(e) => setNewMember({ ...newMember, email: e.target.value })} />
              <label>Password</label>
              <input required type="password" value={newMember.password} onChange={(e) => setNewMember({ ...newMember, password: e.target.value })} />
              <label>Role</label>
              <select value={newMember.role} onChange={(e) => setNewMember({ ...newMember, role: e.target.value })}>
                <option value="employee">Employee</option>
                <option value="admin">Admin</option>
              </select>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowAddModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={saving}>{saving ? "Adding..." : "Add Member"}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}