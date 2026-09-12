import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Code2, UserPlus } from "lucide-react";

/** Pull a readable message out of DRF / network errors (not just username hints). */
function formatRegisterError(err) {
  const fallback = "Registration failed. Please check your details and try again.";
  if (!err.response) {
    return "Cannot reach the server. Make sure the backend is running on port 8000.";
  }
  const data = err.response.data;
  if (!data) return fallback;
  if (typeof data === "string") {
    const trimmed = data.trim();
    return trimmed && !trimmed.startsWith("<") ? trimmed.slice(0, 240) : fallback;
  }
  if (data.detail) {
    return Array.isArray(data.detail) ? String(data.detail[0]) : String(data.detail);
  }
  const messages = [];
  for (const [field, value] of Object.entries(data)) {
    const label = field === "non_field_errors" ? "" : `${field}: `;
    if (Array.isArray(value)) {
      value.forEach((v) => messages.push(`${label}${v}`));
    } else if (typeof value === "string") {
      messages.push(`${label}${value}`);
    }
  }
  return messages.length ? messages.join(" ") : fallback;
}

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(form);
      navigate("/dashboard"); // new signups always default to role='user'
    } catch (err) {
      setError(formatRegisterError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 via-white to-slate-100 px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-6">
          <div className="h-12 w-12 rounded-2xl bg-brand-600 flex items-center justify-center shadow-lg shadow-brand-600/20 mb-3">
            <Code2 className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-slate-900">Create your account</h1>
          <p className="text-sm text-slate-500 mt-1">Start tracking your DSA practice</p>
        </div>

        <form onSubmit={handleSubmit} className="card p-6 space-y-4">
          {error && (
            <div className="bg-red-50 text-red-600 text-sm px-3 py-2 rounded-lg">{error}</div>
          )}
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
            <input
              className="input"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input
              className="input"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
            <input
              className="input"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="At least 8 chars, not too common"
              minLength={8}
              required
            />
            <p className="text-xs text-slate-400 mt-1">
              Use 8+ characters. Avoid common or all-numeric passwords.
            </p>
          </div>
          <button type="submit" disabled={loading} className="btn btn-primary w-full">
            <UserPlus className="h-4 w-4" /> {loading ? "Creating..." : "Create account"}
          </button>
        </form>

        <p className="text-center text-sm text-slate-500 mt-4">
          Already have an account?{" "}
          <Link to="/login" className="text-brand-600 font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
