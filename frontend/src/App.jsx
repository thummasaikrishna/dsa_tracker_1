import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { RequireAdmin, RequireAuth, RequireStudent } from "./routes/ProtectedRoute";
import Navbar from "./components/Navbar";
import Login from "./pages/Login";
import GoogleAuthCallback from "./pages/GoogleAuthCallback";
import Register from "./pages/Register";
import UserDashboard from "./pages/UserDashboard";
import QuestionDetail from "./pages/QuestionDetail";
import RemovedAccount from "./pages/RemovedAccount";
import AdminDashboard from "./pages/AdminDashboard";
import Leaderboard from "./pages/Leaderboard";
import Spinner from "./components/Spinner";

function Layout({ children }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      {children}
    </div>
  );
}

function RootRedirect() {
  const { user, loading, isAdmin } = useAuth();
  if (loading) return <Spinner full />;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={isAdmin ? "/admin" : "/dashboard"} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback" element={<GoogleAuthCallback />} />
          <Route path="/register" element={<Register />} />
          <Route path="/removed" element={<RemovedAccount />} />

          <Route element={<RequireStudent />}>
            <Route
              path="/dashboard"
              element={
                <Layout>
                  <UserDashboard />
                </Layout>
              }
            />
            <Route
              path="/questions/:id"
              element={
                <Layout>
                  <QuestionDetail />
                </Layout>
              }
            />
          </Route>

          <Route element={<RequireAdmin />}>
            <Route
              path="/admin"
              element={
                <Layout>
                  <AdminDashboard />
                </Layout>
              }
            />
          </Route>

          <Route element={<RequireAuth />}>
            <Route
              path="/leaderboard"
              element={
                <Layout>
                  <Leaderboard />
                </Layout>
              }
            />
          </Route>

          <Route path="/" element={<RootRedirect />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}