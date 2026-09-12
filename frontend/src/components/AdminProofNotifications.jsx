/**
 * In-app admin notifications for LinkedIn proofs, inactivity, and code submissions.
 * Persisted notifications are marked read on click and removed with X (server-side dismiss).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, X } from "lucide-react";
import api from "../api/axios";

const POLL_MS = 20_000;

export default function AdminProofNotifications() {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [codeNotes, setCodeNotes] = useState([]);
  const [proofNotes, setProofNotes] = useState([]);
  const panelRef = useRef(null);
  const navigate = useNavigate();

  const fetchPending = useCallback(async () => {
    try {
      const { data: notes } = await api.get("/notifications/");
      // Axios already returns the JSON body in `data`; the backend response
      // is `{ unread_count, items }`, not a nested `{ data: { items } }`.
      // The old path silently produced an empty dropdown even though the
      // submission notification had been created successfully.
      const allNotes = notes.items ?? [];
      setAlerts(allNotes.filter((n) => n.event === "student_inactive"));
      setCodeNotes(allNotes.filter((n) => n.event === "code_submitted"));
      setProofNotes(allNotes.filter((n) => n.event === "proof_submitted"));
    } catch {
      /* ignore — admin may be logged out mid-poll */
    }
  }, []);

  useEffect(() => {
    fetchPending();
    const id = setInterval(fetchPending, POLL_MS);

    function onFocus() {
      fetchPending();
    }
    function onVisibility() {
      if (document.visibilityState === "visible") fetchPending();
    }
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetchPending]);

  useEffect(() => {
    function onDocClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  function markLocalRead(n) {
    const apply = (list) => list.map((x) => (x.id === n.id ? { ...x, is_read: true } : x));
    setAlerts(apply);
    setCodeNotes(apply);
    setProofNotes(apply);
  }

  async function markRead(n) {
    if (n.is_read) return;
    try {
      await api.post(`/notifications/${n.id}/read/`);
      markLocalRead(n);
    } catch {
      /* still navigate */
    }
  }

  async function dismissItem(e, n) {
    e.preventDefault();
    e.stopPropagation();
    try {
      await api.patch(`/notifications/${n.id}/dismiss/`);
      setAlerts((list) => list.filter((x) => x.id !== n.id));
      setCodeNotes((list) => list.filter((x) => x.id !== n.id));
      setProofNotes((list) => list.filter((x) => x.id !== n.id));
    } catch {
      /* ignore */
    }
  }

  async function openProof(n) {
    setOpen(false);
    await markRead(n);
    if (n.assignment_id) navigate(`/admin?tab=proofs&highlight=${n.assignment_id}`);
    else navigate("/admin?tab=proofs");
  }

  async function openCodeSubmission(n) {
    setOpen(false);
    await markRead(n);
    if (n.code_submission_id) {
      navigate(`/admin?tab=submissions&highlight=${n.code_submission_id}`);
    } else {
      navigate("/admin?tab=submissions");
    }
  }

  function openAllPending() {
    setOpen(false);
    navigate("/admin?tab=proofs");
  }

  async function openInactivity(n) {
    setOpen(false);
    await markRead(n);
    navigate("/admin?tab=students");
  }

  const badge = [...alerts, ...codeNotes, ...proofNotes].filter((n) => !n.is_read).length;

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          fetchPending();
        }}
        className="relative p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors"
        aria-label="Admin notifications"
        title="Notifications"
      >
        <Bell className="h-4 w-4" />
        {badge > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center leading-none">
            {badge > 99 ? "99+" : badge}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 card shadow-lg z-30 overflow-hidden">
          <div className="px-3 py-2.5 border-b border-slate-100 flex items-center justify-between bg-slate-50">
            <span className="text-sm font-semibold text-slate-800">Notifications</span>
            {badge > 0 && (
              <span className="text-xs font-medium text-rose-600">{badge} new</span>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {alerts.length > 0 && (
              <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-amber-700 bg-amber-50">
                Student inactivity
              </div>
            )}
            {alerts.map((n) => (
              <div
                key={`inact-${n.id}`}
                className={`flex items-start gap-1 border-b border-slate-50 ${
                  n.is_read ? "" : "bg-amber-50/70"
                }`}
              >
                <button
                  type="button"
                  onClick={() => openInactivity(n)}
                  className="flex-1 min-w-0 text-left px-3 py-2.5 hover:bg-amber-50 transition-colors"
                >
                  <div className="text-sm font-medium text-slate-900">Student Inactivity Alert</div>
                  <div className="text-xs text-slate-600 mt-0.5">
                    Student {n.about_username || "Unknown"} has not performed any DSA activity.
                  </div>
                  {n.message && (
                    <div className="text-[11px] text-slate-400 mt-1 line-clamp-2">{n.message}</div>
                  )}
                </button>
                <button
                  type="button"
                  aria-label="Remove notification"
                  title="Remove"
                  onClick={(e) => dismissItem(e, n)}
                  className="shrink-0 mt-2 mr-2 p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
            {codeNotes.length > 0 && (
              <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-brand-700 bg-brand-50">
                Code submissions
              </div>
            )}
            {codeNotes.map((n) => (
              <div
                key={`code-${n.id}`}
                className={`flex items-start gap-1 border-b border-slate-50 ${
                  n.is_read ? "" : "bg-brand-50/70"
                }`}
              >
                <button
                  type="button"
                  onClick={() => openCodeSubmission(n)}
                  className="flex-1 min-w-0 text-left px-3 py-2.5 hover:bg-brand-50 transition-colors"
                >
                  <div className="text-sm font-medium text-slate-900">NEW CODE SUBMISSION</div>
                  <div className="text-xs text-slate-600 mt-0.5 whitespace-pre-line line-clamp-4">{n.message}</div>
                  <div className="text-[11px] font-medium text-brand-700 mt-1">View Submission</div>
                </button>
                <button
                  type="button"
                  aria-label="Remove notification"
                  title="Remove"
                  onClick={(e) => dismissItem(e, n)}
                  className="shrink-0 mt-2 mr-2 p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
            {proofNotes.length > 0 && (
              <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500 bg-slate-50">
                Proof submissions
              </div>
            )}
            {proofNotes.map((n) => (
              <div key={`proof-${n.id}`} className={`flex items-start gap-1 border-b border-slate-50 ${n.is_read ? "" : "bg-brand-50/70"}`}>
                <button type="button" onClick={() => openProof(n)} className="flex-1 min-w-0 text-left px-3 py-2.5 hover:bg-brand-50 transition-colors">
                  <div className="text-sm font-medium text-slate-900">NEW PROOF SUBMISSION</div>
                  <div className="text-xs text-slate-600 mt-0.5 whitespace-pre-line line-clamp-3">{n.message}</div>
                  <div className="text-[11px] font-medium text-brand-700 mt-1">Review Proof</div>
                </button>
                <button type="button" aria-label="Remove notification" title="Remove" onClick={(e) => dismissItem(e, n)} className="shrink-0 mt-2 mr-2 p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
            {alerts.length + codeNotes.length + proofNotes.length === 0 && (
              <div className="px-4 py-6 text-center text-sm text-slate-400">No notifications yet.</div>
            )}
          </div>
          {proofNotes.length > 0 && (
            <button
              type="button"
              onClick={openAllPending}
              className="w-full px-3 py-2 text-xs font-medium text-brand-700 hover:bg-brand-50 border-t border-slate-100"
            >
              Open Proof Validation
            </button>
          )}
        </div>
      )}
    </div>
  );
}
