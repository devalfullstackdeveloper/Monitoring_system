import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listUsers, listTimeEntries } from "../api";

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export default function Timesheets() {
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [entries, setEntries] = useState([]);

  useEffect(() => {
    listUsers().then(setUsers);
  }, []);

  useEffect(() => {
    listTimeEntries(selectedUserId || undefined).then(setEntries);
  }, [selectedUserId]);

  return (
    <div>
      <h1>Timesheets</h1>
      <div className="card">
        <label>Filter by user: </label>
        <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
          <option value="">All</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Start</th>
              <th>End</th>
              <th>Duration</th>
              <th>Status</th>
              <th>Screenshots</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{users.find((u) => u.id === e.user_id)?.name || e.user_id}</td>
                <td>{new Date(e.start_time).toLocaleString()}</td>
                <td>{e.end_time ? new Date(e.end_time).toLocaleString() : "-"}</td>
                <td>{formatDuration(e.duration_seconds)}</td>
                <td>{e.status}</td>
                <td>
                  <Link to={`/screenshots?time_entry_id=${e.id}`}>View</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
