import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import EmployeeDetail from "./pages/EmployeeDetail.jsx";
import EmployeeScreenshots from "./pages/EmployeeScreenshots.jsx";
import Timesheets from "./pages/Timesheets.jsx";
import Screenshots from "./pages/Screenshots.jsx";
import { getCurrentUser, logout } from "./api";
import logo from "./assets/org-tracker-logo.svg";

function isAuthenticated() {
  return !!localStorage.getItem("token");
}

function RequireAuth({ children }) {
  return isAuthenticated() ? children : <Navigate to="/login" replace />;
}

function Shell({ children }) {
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    getCurrentUser().then(setCurrentUser).catch(() => setCurrentUser(null));
  }, []);

  const userInitials = currentUser?.name
    ? currentUser.name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()
    : "--";
  const roleLabel = currentUser?.role === "admin" ? "Administrator" : "Employee";

  return (
    <div className="app-shell">
      <div className="sidebar">
        <div className="brand-mark">
          <img className="brand-logo" src={logo} alt="Org Tracker" />
          <div><strong>Org Tracker</strong><small>IT IDOL</small></div>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/"><span className="nav-icon">⌂</span>Dashboard</NavLink>
          <NavLink to="/timesheets"><span className="nav-icon">◷</span>Timesheets</NavLink>
          <NavLink to="/screenshots"><span className="nav-icon">▣</span>Screenshots</NavLink>
        </nav>
        <div className="sidebar-footer">
          <div className="admin-profile"><span className="admin-avatar">{userInitials}</span><div><strong>{currentUser?.name || "Loading..."}</strong><small>{currentUser?.email || ""}</small></div></div>
          <div className="profile-role">{roleLabel}</div>
          <a href="#" onClick={() => { logout(); window.location.href = "/login"; }}><span className="nav-icon">↪</span>Sign Out</a>
        </div>
      </div>
      <div className="content">{children}</div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <Shell><Dashboard /></Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/employee/:id"
          element={
            <RequireAuth>
              <Shell><EmployeeDetail /></Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/employee/:id/screenshots"
          element={
            <RequireAuth>
              <Shell><EmployeeScreenshots /></Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/timesheets"
          element={
            <RequireAuth>
              <Shell><Timesheets /></Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/screenshots"
          element={
            <RequireAuth>
              <Shell><Screenshots /></Shell>
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}