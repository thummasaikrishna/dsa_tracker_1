export default function Spinner({ full }) {
  const el = (
    <div className="flex items-center justify-center py-10">
      <div className="h-8 w-8 border-4 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
    </div>
  );
  if (full) {
    return <div className="min-h-screen flex items-center justify-center bg-slate-50">{el}</div>;
  }
  return el;
}
