import LeaderboardView from "../components/LeaderboardView";
import { useAuth } from "../context/AuthContext";

export default function Leaderboard() {
  const { isAdmin } = useAuth();
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">🏆 Leaderboard</h1>
      <p className="text-sm text-slate-500 mb-6">
        Rankings use validated points only. Ties go to more solved problems, then the earlier latest validation.
      </p>
      <LeaderboardView showAdminActivity={isAdmin} />
    </div>
  );
}
