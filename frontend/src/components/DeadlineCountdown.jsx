import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { formatDateTime, formatRemaining } from "../utils/datetime";

export default function DeadlineCountdown({ createdAt, deadline, remainingSeconds, deadlineExpired, compact = false }) {
  const initial = Number.isFinite(remainingSeconds)
    ? remainingSeconds
    : deadline
      ? Math.max(0, Math.floor((new Date(deadline).getTime() - Date.now()) / 1000))
      : 0;
  const [left, setLeft] = useState(initial);
  const expired = deadlineExpired || left <= 0;

  useEffect(() => {
    const next = Number.isFinite(remainingSeconds)
      ? remainingSeconds
      : deadline
        ? Math.max(0, Math.floor((new Date(deadline).getTime() - Date.now()) / 1000))
        : 0;
    setLeft(next);
  }, [remainingSeconds, deadline]);

  useEffect(() => {
    if (expired) return undefined;
    const id = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [expired]);

  const remainingLabel = formatRemaining(left);

  if (compact) {
    if (expired) {
      return <span className="text-xs font-medium text-rose-600 whitespace-nowrap">🔴 Deadline Expired</span>;
    }
    return (
      <span className="text-xs text-slate-500 whitespace-nowrap inline-flex items-center gap-1">
        <Clock className="h-3 w-3" /> {remainingLabel} remaining
      </span>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 space-y-1.5">
      <div className="text-sm text-slate-600">
        <span className="font-medium text-slate-800">Published:</span> {formatDateTime(createdAt)}
      </div>
      <div className="text-sm text-slate-600">
        <span className="font-medium text-slate-800">Deadline:</span> {formatDateTime(deadline)}
      </div>
      {expired ? (
        <div className="text-sm font-semibold text-rose-600">🔴 Deadline Expired</div>
      ) : (
        <div className="text-sm font-medium text-brand-700 inline-flex items-center gap-1.5">
          ⏰ {remainingLabel} remaining
        </div>
      )}
    </div>
  );
}
