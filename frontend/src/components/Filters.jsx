/**
 * Shared filter bar (difficulty pills + time-period select + status).
 *
 * TECHNIQUE: Controlled filters lifted to the parent. This component is
 * "dumb" — it just renders the current filter state and calls back on
 * change. The parent owns the state and decides when to re-fetch, which
 * lets us debounce/batch requests instead of firing one per click deep
 * inside a child component.
 */
const DIFFICULTIES = [
  { value: "", label: "All" },
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

const PERIODS = [
  { value: "7days", label: "Last 7 Days" },
  { value: "30days", label: "Last 30 Days" },
  { value: "all", label: "All Time" },
];

const STATUSES = [
  { value: "", label: "All Status" },
  { value: "assigned", label: "Assigned" },
  { value: "in_progress", label: "In Progress" },
  { value: "completed", label: "Completed" },
];

export function DifficultyFilter({ value, onChange }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {DIFFICULTIES.map((d) => (
        <button
          key={d.value}
          onClick={() => onChange(d.value)}
          className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
            value === d.value
              ? "bg-brand-600 text-white border-brand-600"
              : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
          }`}
        >
          {d.label}
        </button>
      ))}
    </div>
  );
}

export function PeriodSelect({ value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="input !w-auto text-sm">
      {PERIODS.map((p) => (
        <option key={p.value} value={p.value}>
          {p.label}
        </option>
      ))}
    </select>
  );
}

export function StatusFilter({ value, onChange, counts }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {STATUSES.map((s) => {
        const countKey = s.value === "" ? "all" : s.value;
        const count = counts ? counts[countKey] : null;
        return (
          <button
            key={s.value}
            onClick={() => onChange(s.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
              value === s.value
                ? "bg-slate-800 text-white border-slate-800"
                : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
            }`}
          >
            {s.label}
            {count != null && (
              <span className={`ml-1.5 font-semibold ${value === s.value ? "text-white" : "text-slate-800"}`}>
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
