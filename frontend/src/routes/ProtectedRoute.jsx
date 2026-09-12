/**
 * Route guards.
 *
 * TECHNIQUE: Declarative route protection. Instead of checking
 * `if (!user) redirect()` inside every page component, we wrap routes
 * with a guard component. `<Outlet />` renders the matched child route
 * only if the guard's condition passes — otherwise it issues a
 * `<Navigate>` redirect. This keeps auth/role checks in ONE place.
 */
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Spinner from "../components/Spinner";

export function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner full />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.is_removed) return <Navigate to="/removed" replace />;
  return <Outlet />;
}

export function RequireStudent() {
  const { user, loading, isAdmin } = useAuth();
  if (loading) return <Spinner full />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.is_removed) return <Navigate to="/removed" replace />;
  if (isAdmin) return <Navigate to="/admin" replace />;
  return <Outlet />;
}

export function RequireAdmin() {
  const { user, loading, isAdmin } = useAuth();
  if (loading) return <Spinner full />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.is_removed) return <Navigate to="/removed" replace />;
  if (!isAdmin) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}
