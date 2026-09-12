import { useCallback, useEffect, useState } from "react";
import { Trophy, Medal, Star, CheckCircle2 } from "lucide-react";
import api from "../api/axios";
import Spinner from "./Spinner";
import { formatDateTime } from "../utils/datetime";

function rankMark(rank) {
  if (rank === 1) return "🥇";
  if (rank === 2) return "🥈";
  if (rank === 3) return "🥉";
  return String(rank);
}

export default function LeaderboardView({ showAdminActivity = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    api
      .get("/analytics/leaderboard/")
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 20_000);
    function onFocus() {
      load();
    }
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  if (loading) return <Spinner />;
  if (!data) {
    return <div className="text-center py-14 text-slate-400 text-sm">Could not load the leaderboard.</div>;
  }

  const me = data.me;
  const items = data.items ?? [];
  const isAdmin = data.is_admin;

  return (
    <div className="space-y-5">
      {me && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="card p-4 flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-amber-50 text-amber-700 flex items-center justify-center">
              <Trophy className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs text-slate-500">Your Rank</div>
              <div className="text-xl font-bold text-slate-900">#{me.rank}</div>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-brand-50 text-brand-700 flex items-center justify-center">
              <Star className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs text-slate-500">Total Points</div>
              <div className="text-xl font-bold text-slate-900">{me.total_points}</div>
            </div>
          </div>
          <div className="card p-4 flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-emerald-50 text-emerald-700 flex items-center justify-center">
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <div>
              <div className="text-xs text-slate-500">Problems Solved</div>
              <div className="text-xl font-bold text-slate-900">{me.solved_count}</div>
            </div>
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2 bg-slate-50">
          <Medal className="h-4 w-4 text-amber-600" />
          <h2 className="text-sm font-semibold text-slate-800">🏆 Leaderboard</h2>
          <span className="text-xs text-slate-400 ml-auto">{items.length} active student{items.length === 1 ? "" : "s"}</span>
        </div>
        {items.length === 0 ? (
          <div className="text-center py-14 text-slate-400 text-sm">No active students yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white text-slate-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Rank</th>
                <th className="px-4 py-3 font-medium">Student</th>
                <th className="px-4 py-3 font-medium">Points</th>
                <th className="px-4 py-3 font-medium">Solved</th>
                {(isAdmin || showAdminActivity) && (
                  <th className="px-4 py-3 font-medium hidden sm:table-cell">Recent Activity</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((row) => (
                <tr
                  key={row.user_id}
                  className={row.is_me ? "bg-brand-50/70" : "hover:bg-slate-50"}
                >
                  <td className="px-4 py-3 font-semibold text-slate-800 whitespace-nowrap">
                    {rankMark(row.rank)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">
                      {row.display_name}
                      {row.is_me && (
                        <span className="ml-2 text-[11px] font-semibold text-brand-700 bg-white border border-brand-200 rounded-full px-2 py-0.5">
                          You
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400">@{row.username}</div>
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-900">{row.total_points}</td>
                  <td className="px-4 py-3 text-slate-600">{row.solved_count}</td>
                  {(isAdmin || showAdminActivity) && (
                    <td className="px-4 py-3 text-xs text-slate-500 hidden sm:table-cell">
                      {row.last_validated_at
                        ? `Validated ${formatDateTime(row.last_validated_at)}`
                        : row.last_activity_at
                          ? `Active ${formatDateTime(row.last_activity_at)}`
                          : "No activity yet"}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
