export default function FlashBanner({ message, type = "success", onClose }) {
  if (!message) return null;
  const styles =
    type === "error"
      ? "bg-red-50 text-red-700 border-red-200"
      : "bg-emerald-50 text-emerald-800 border-emerald-200";
  return (
    <div className={`mb-4 text-sm px-3 py-2 rounded-lg border flex items-start justify-between gap-3 ${styles}`} role="status">
      <span>{message}</span>
      {onClose && (
        <button type="button" onClick={onClose} className="text-xs opacity-70 hover:opacity-100 shrink-0">
          Dismiss
        </button>
      )}
    </div>
  );
}
