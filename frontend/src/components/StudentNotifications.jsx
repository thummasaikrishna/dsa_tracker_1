/**
 * Student in-app notifications: new questions + validated proofs.
 * Persisted on the server so refresh does not duplicate events.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, X } from "lucide-react";
import api from "../api/axios";

const POLL_MS = 20_000;

export default function StudentNotifications() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const panelRef = useRef(null);
  const navigate = useNavigate();

  const fetchNotes = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications/");
      setUnread(data.unread_count ?? 0);
      setItems(data.items ?? []);
    } catch {
      /* ignore mid-poll logout */
    }
  }, []);

  useEffect(() => {
    fetchNotes();
    const id = setInterval(fetchNotes, POLL_MS);
    function onFocus() {
      fetchNotes();
    }
    function onVisibility() {
      if (document.visibilityState === "visible") fetchNotes();
    }
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetchNotes]);

  useEffect(() => {
    function onDocClick(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  async function dismissItem(e, n) {
    e.preventDefault();
    e.stopPropagation();
    try {
      await api.patch(`/notifications/${n.id}/dismiss/`);
      setItems((list) => list.filter((x) => x.id !== n.id));
      if (!n.is_read) setUnread((c) => Math.max(0, c - 1));
    } catch {
      /* ignore */
    }
  }

  async function openItem(n) {
    setOpen(false);
    if (!n.is_read) {
      try {
        await api.post(`/notifications/${n.id}/read/`);
        setItems((list) => list.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
        setUnread((c) => Math.max(0, c - 1));
      } catch {
        /* still navigate */
      }
    }
    if (n.event === "proof_validated" && n.assignment_id) {
      navigate(`/dashboard?tab=mine&highlight=${n.assignment_id}`);
      return;
    }
    if (n.event === "proof_rejected" && n.assignment_id) {
      navigate(`/dashboard?tab=mine&highlight=${n.assignment_id}`);
      return;
    }
    if (n.event === "code_result" && n.question_id) {
      navigate(`/questions/${n.question_id}`);
      return;
    }
    if ((n.event === "new_question" || n.event === "question_updated") && n.question_id) {
      navigate(`/questions/${n.question_id}`);
      return;
    }
    if (n.question_id) {
      navigate(`/questions/${n.question_id}`);
    }
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          fetchNotes();
        }}
        className="relative p-2 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors"
        aria-label="Notifications"
        title="Notifications"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center leading-none">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 card shadow-lg z-30 overflow-hidden">
          <div className="px-3 py-2.5 border-b border-slate-100 flex items-center justify-between bg-slate-50">
            <span className="text-sm font-semibold text-slate-800">Notifications</span>
            {unread > 0 && (
              <span className="text-xs font-medium text-brand-700">{unread} new</span>
            )}
          </div>
          <div className="max-h-72 overflow-y-auto">
            {items.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-slate-400">No notifications yet.</div>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  className={`flex items-start gap-1 border-b border-slate-50 last:border-0 ${
                    n.is_read ? "" : "bg-brand-50/50"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => openItem(n)}
                    className="flex-1 min-w-0 text-left px-3 py-2.5 hover:bg-brand-50 transition-colors"
                  >
                    <div className="text-sm font-medium text-slate-900">{n.title}</div>
                    {n.question_title && (
                      <div className="text-xs text-slate-600 mt-0.5 truncate">
                        {n.event === "question_updated" ? "Question Updated: " : "Problem: "}
                        {n.question_title}
                        {n.difficulty ? ` · ${n.difficulty.charAt(0).toUpperCase()}${n.difficulty.slice(1)}` : ""}
                      </div>
                    )}
                    {n.message && n.event !== "new_question" && (
                      <div className="text-xs text-slate-500 mt-0.5 whitespace-pre-line line-clamp-3">{n.message}</div>
                    )}
                    {n.created_at && (
                      <div className="text-[11px] text-slate-400 mt-1">
                        {new Date(n.created_at).toLocaleString()}
                      </div>
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
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
