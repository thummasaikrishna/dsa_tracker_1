import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

/**
 * Renders the difficulty breakdown returned by /analytics/my-activity/
 * (or /analytics/student/{id}/) as summary tiles + a bar chart.
 *
 * The breakdown numbers come pre-aggregated from the backend (a single
 * SQL query with conditional COUNT), so this component does zero
 * client-side counting — it just visualizes numbers it's given.
 */
export default function ActivityStats({ breakdown, statusBreakdown, completedBreakdown }) {
  const chartData = [
    { name: "Easy", count: breakdown.easy, fill: "#10b981" },
    { name: "Medium", count: breakdown.medium, fill: "#f59e0b" },
    { name: "Hard", count: breakdown.hard, fill: "#f43f5e" },
  ];

  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div className="card p-5">
        <div className="text-sm text-slate-500 mb-3">Total Assigned</div>
        <div className="text-3xl font-bold text-slate-900 mb-4">{breakdown.total}</div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-emerald-50 rounded-lg py-2">
            <div className="text-lg font-bold text-emerald-700">{breakdown.easy}</div>
            <div className="text-xs text-emerald-600">Easy</div>
          </div>
          <div className="bg-amber-50 rounded-lg py-2">
            <div className="text-lg font-bold text-amber-700">{breakdown.medium}</div>
            <div className="text-xs text-amber-600">Medium</div>
          </div>
          <div className="bg-rose-50 rounded-lg py-2">
            <div className="text-lg font-bold text-rose-700">{breakdown.hard}</div>
            <div className="text-xs text-rose-600">Hard</div>
          </div>
        </div>
        {statusBreakdown && (
          <div className="grid grid-cols-3 gap-2 text-center mt-3 pt-3 border-t border-slate-100">
            <div>
              <div className="text-sm font-semibold text-slate-700">{statusBreakdown.assigned}</div>
              <div className="text-xs text-slate-400">Assigned</div>
            </div>
            <div>
              <div className="text-sm font-semibold text-blue-700">{statusBreakdown.in_progress}</div>
              <div className="text-xs text-slate-400">In Progress</div>
            </div>
            <div>
              <div className="text-sm font-semibold text-emerald-700">{statusBreakdown.completed}</div>
              <div className="text-xs text-slate-400">Completed</div>
            </div>
          </div>
        )}
        {completedBreakdown && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <div className="text-xs text-slate-500 mb-2">Completed by difficulty</div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div>
                <div className="text-sm font-semibold text-emerald-700">{completedBreakdown.easy}</div>
                <div className="text-xs text-slate-400">Easy done</div>
              </div>
              <div>
                <div className="text-sm font-semibold text-amber-700">{completedBreakdown.medium}</div>
                <div className="text-xs text-slate-400">Medium done</div>
              </div>
              <div>
                <div className="text-sm font-semibold text-rose-700">{completedBreakdown.hard}</div>
                <div className="text-xs text-slate-400">Hard done</div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="card p-5">
        <div className="text-sm text-slate-500 mb-3">Difficulty Breakdown</div>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} width={24} />
            <Tooltip cursor={{ fill: "#f8fafc" }} />
            <Bar dataKey="count" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
