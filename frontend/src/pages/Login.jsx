import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { isRemovedError } from "../api/axios";
import { isSupabaseConfigured, supabase } from "../api/supabase";
import { Code2, LogIn } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleGoogleLogin() {
    setError("");
    if (!isSupabaseConfigured) {
      setError("Google sign-in is not configured for this environment.");
      return;
    }
    setLoading(true);
    const { error: oauthError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (oauthError) {
      setError("Google sign-in could not be started. Please try again.");
      setLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const me = await login(form.username, form.password);
      navigate(me.role === "admin" ? "/admin" : "/dashboard");
    } catch (err) {
      if (isRemovedError(err) || err.code === "account_removed") {
        navigate("/removed", { replace: true });
        return;
      }
      setError(
        typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Invalid username or password."
      );
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
          <h1 className="text-xl font-bold text-slate-900">Welcome back</h1>
          <p className="text-sm text-slate-500 mt-1">Sign in to your DSA Tracker account</p>
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
              placeholder="username or email"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
            <input
              className="input"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              placeholder="••••••••"
              required
            />
          </div>
          <button type="submit" disabled={loading} className="btn btn-primary w-full">
            <LogIn className="h-4 w-4" /> {loading ? "Signing in..." : "Sign in"}
          </button>
          <button type="button" disabled={loading} onClick={handleGoogleLogin} className="btn btn-secondary w-full">
            Continue with Google
          </button>
        </form>

        <p className="text-center text-sm text-slate-500 mt-4">
          Don't have an account?{" "}
          <Link to="/register" className="text-brand-600 font-medium hover:underline">
            Create one
          </Link>
        </p>

        <div className="mt-6 text-xs text-slate-400 text-center leading-relaxed">
          Demo accounts (after running <code className="bg-slate-100 px-1 rounded">seed_demo</code>):
          <br />
          Admin: saikrishnathumma &nbsp;•&nbsp; Student: rahul / Student@123
        </div>
      </div>
    </div>
  );
}
