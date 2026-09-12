import { Link } from "react-router-dom";
import { DifficultyBadge } from "./Badges";
import DeadlineCountdown from "./DeadlineCountdown";
import { Check, ChevronRight } from "lucide-react";

/** Compact syllabus-style row for browsing questions. */
export default function QuestionCard({ question }) {
  return (
    <Link
      to={`/questions/${question.id}`}
      className="flex items-center gap-3 px-4 py-3.5 hover:bg-slate-50 transition-colors group"
    >
      <div className="flex-1 min-w-0">
        <div className="font-medium text-slate-900 group-hover:text-brand-700 transition-colors">
          {question.title}
        </div>
        <div className="mt-1">
          <DeadlineCountdown
            createdAt={question.created_at}
            deadline={question.deadline}
            remainingSeconds={question.remaining_seconds}
            deadlineExpired={question.deadline_expired}
            compact
          />
        </div>
      </div>
      <DifficultyBadge difficulty={question.difficulty} />
      {question.is_assigned_to_me && (
        <span className="text-xs text-emerald-600 font-medium inline-flex items-center gap-1 shrink-0">
          <Check className="h-3.5 w-3.5" /> Assigned
        </span>
      )}
      <ChevronRight className="h-4 w-4 text-slate-300 group-hover:text-slate-500 shrink-0" />
    </Link>
  );
}
