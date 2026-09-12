import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { isRemovedError } from "../api/axios";
import { isSupabaseConfigured, supabase } from "../api/supabase";
import Spinner from "../components/Spinner";

function safeResponseBody(data) {
  if (!data || typeof data !== "object") return typeof data === "string" ? data.slice(0, 300) : null;
  return Object.fromEntries(
    Object.entries(data).map(([key, value]) => [
      key,
      /token|secret|authorization|password|key/i.test(key) ? "<redacted>" : value,
    ])
  );
}

export default function GoogleAuthCallback() {
  const { completeGoogleLogin } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const hasStarted = useRef(false);

  useEffect(() => {
    if (hasStarted.current) return;
    hasStarted.current = true;

    async function finishGoogleLogin() {
      if (!isSupabaseConfigured) {
        setError("Google sign-in is not configured for this environment.");
        return;
      }
      let stage = "read_callback";
      try {
        const code = new URLSearchParams(window.location.search).get("code");
        if (code) {
          stage = "exchange_supabase_code";
          const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
          if (exchangeError) throw exchangeError;
        }
        stage = "read_supabase_session";
        const { data: { session } } = await supabase.auth.getSession();
        if (!session?.access_token) throw new Error("No Google session available");
        stage = "exchange_with_django";
        const me = await completeGoogleLogin(session.access_token);
        navigate(me.role === "admin" ? "/admin" : "/dashboard", { replace: true });
      } catch (err) {
        const diagnostic = {
          stage,
          name: err?.name || "Error",
          message: String(err?.message || "").slice(0, 300),
          status: err?.response?.status || null,
          contentType: err?.response?.headers?.["content-type"] || null,
          response: safeResponseBody(err?.response?.data),
        };
        if (import.meta.env.DEV) window.__googleOAuthDiagnostic = diagnostic;
        console.error("Google OAuth callback failed", JSON.stringify(diagnostic));
        if (isRemovedError(err) || err.code === "account_removed") {
          navigate("/removed", { replace: true });
          return;
        }
        setError("Google sign-in could not be completed. Please try again.");
      }
    }
    finishGoogleLogin();
  }, [completeGoogleLogin, navigate]);

  if (!error) return <Spinner full />;
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="card max-w-sm p-6 text-center">
        <p className="text-sm text-red-600">{error}</p>
        <button type="button" className="btn btn-primary mt-4" onClick={() => navigate("/login", { replace: true })}>
          Back to sign in
        </button>
      </div>
    </div>
  );
}
