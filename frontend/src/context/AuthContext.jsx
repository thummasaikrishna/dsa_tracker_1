/**
 * AuthContext — a single source of truth for "who is logged in" and
 * "what role do they have", using React's Context API instead of prop
 * drilling `user` / `role` through every component tree.
 */
import { createContext, useContext, useEffect, useState } from "react";
import api, { clearTokens, isRemovedError } from "../api/axios";
import { supabase } from "../api/supabase";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadMe() {
    const access = localStorage.getItem("access");
    if (!access) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get("/auth/me/");
      if (data.is_removed) {
        clearTokens();
        setUser(null);
        window.location.href = "/removed";
        return;
      }
      setUser(data);
    } catch (err) {
      if (isRemovedError(err)) {
        clearTokens();
        setUser(null);
        window.location.href = "/removed";
        return;
      }
      clearTokens();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMe();
  }, []);

  async function login(username, password) {
    clearTokens();
    setUser(null);
    const { data } = await api.post("/auth/login/", { username, password });
    localStorage.setItem("access", data.access);
    localStorage.setItem("refresh", data.refresh);
    const { data: me } = await api.get("/auth/me/");
    if (me.is_removed) {
      clearTokens();
      setUser(null);
      const err = new Error("ACCOUNT_REMOVED");
      err.code = "account_removed";
      throw err;
    }
    setUser(me);
    return me;
  }

  async function register(payload) {
    clearTokens();
    setUser(null);
    const { data } = await api.post("/auth/register/", payload);
    localStorage.setItem("access", data.access);
    localStorage.setItem("refresh", data.refresh);
    const { data: me } = await api.get("/auth/me/");
    setUser(me);
    return me;
  }

  async function completeGoogleLogin(accessToken) {
    clearTokens();
    setUser(null);
    const { data } = await api.post("/auth/supabase/google/", { access_token: accessToken });
    localStorage.setItem("access", data.access);
    localStorage.setItem("refresh", data.refresh);
    const { data: me } = await api.get("/auth/me/");
    if (me.is_removed) {
      clearTokens();
      setUser(null);
      const err = new Error("ACCOUNT_REMOVED");
      err.code = "account_removed";
      throw err;
    }
    setUser(me);
    return me;
  }

  function logout() {
    clearTokens();
    setUser(null);
    if (supabase) {
      supabase.auth.signOut().catch(() => supabase.auth.signOut({ scope: "local" }));
    }
  }

  const isAdmin = user?.role === "admin";

  return (
    <AuthContext.Provider value={{ user, loading, login, register, completeGoogleLogin, logout, isAdmin, reloadMe: loadMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
