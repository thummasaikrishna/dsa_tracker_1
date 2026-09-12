import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import AdminProofNotifications from "./AdminProofNotifications";
import StudentNotifications from "./StudentNotifications";
import { Code2, LogOut, LayoutDashboard, ShieldCheck, Trophy } from "lucide-react";

export default function Navbar() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  const linkClass = ({ isActive }) =>
    `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100"
    }`;

  const displayName = user
    ? [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username
    : "";

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-brand-600 flex items-center justify-center">
            <Code2 className="h-4 w-4 text-white" />
          </div>
          <span className="font-semibold text-slate-900">DSA Tracker</span>
        </div>

        {user && (
          <nav className="flex items-center gap-1">
            {isAdmin ? (
              <NavLink to="/admin" className={linkClass}>
                <span className="inline-flex items-center gap-1.5">
                  <ShieldCheck className="h-3.5 w-3.5" /> Admin
                </span>
              </NavLink>
            ) : (
              <NavLink to="/dashboard" className={linkClass}>
                <span className="inline-flex items-center gap-1.5">
                  <LayoutDashboard className="h-3.5 w-3.5" /> Dashboard
                </span>
              </NavLink>
            )}
            <NavLink to="/leaderboard" className={linkClass}>
              <span className="inline-flex items-center gap-1.5">
                <Trophy className="h-3.5 w-3.5" /> Leaderboard
              </span>
            </NavLink>
          </nav>
        )}

        {user && (
          <div className="flex items-center gap-2 sm:gap-3">
            {isAdmin ? <AdminProofNotifications /> : <StudentNotifications />}
            <div className="text-right hidden sm:block">
              <div className="text-sm font-medium text-slate-900 leading-tight">{displayName}</div>
              <div className="text-xs text-slate-500 leading-tight">
                <span className="capitalize">{user.role === "admin" ? "Admin" : "Student"}</span>
                {user.email ? ` · ${user.email}` : ` · @${user.username}`}
              </div>
            </div>
            <button onClick={handleLogout} className="btn btn-secondary !px-3 !py-1.5">
              <LogOut className="h-3.5 w-3.5" /> Logout
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
