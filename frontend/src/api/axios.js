/**
 * Central axios instance.
 *
 * TECHNIQUE: Token refresh via response interceptor + request queueing.
 * When an access token expires mid-session, the API returns 401. Instead
 * of forcing the user to log in again, we:
 *   1. Catch the 401 in a response interceptor.
 *   2. Use the stored refresh token to silently get a new access token.
 *   3. Retry the ORIGINAL failed request with the new token.
 *   4. Queue any OTHER requests that fail while the refresh is in-flight,
 *      so we don't fire N parallel refresh calls for N simultaneous 401s.
 */
import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api";

const api = axios.create({ baseURL: API_BASE });

function getTokens() {
  return {
    access: localStorage.getItem("access"),
    refresh: localStorage.getItem("refresh"),
  };
}

function setAccessToken(token) {
  localStorage.setItem("access", token);
}

export function clearTokens() {
  localStorage.removeItem("access");
  localStorage.removeItem("refresh");
}

export function isRemovedError(error) {
  const data = error?.response?.data;
  if (!data) return false;
  if (data.code === "account_removed") return true;
  if (data.detail === "ACCOUNT_REMOVED") return true;
  if (typeof data.detail === "object" && data.detail?.code === "account_removed") return true;
  if (typeof data.detail === "object" && data.detail?.detail === "ACCOUNT_REMOVED") return true;
  return false;
}

function redirectRemoved() {
  clearTokens();
  if (window.location.pathname !== "/removed") {
    window.location.href = "/removed";
  }
}

api.interceptors.request.use((config) => {
  const { access } = getTokens();
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

let isRefreshing = false;
let pendingQueue = [];

function flushQueue(error, token = null) {
  pendingQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else resolve(token);
  });
  pendingQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const status = error.response ? error.response.status : null;

    if (isRemovedError(error)) {
      redirectRemoved();
      return Promise.reject(error);
    }

    if (status === 401 && !originalRequest._retry && !originalRequest.url.includes("/auth/")) {
      if (isRefreshing) {
        // Another request already triggered a refresh — wait for it.
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;
      const { refresh } = getTokens();

      if (!refresh) {
        clearTokens();
        window.location.href = "/login";
        return Promise.reject(error);
      }

      try {
        const { data } = await axios.post(`${API_BASE}/auth/refresh/`, { refresh });
        setAccessToken(data.access);
        api.defaults.headers.Authorization = `Bearer ${data.access}`;
        flushQueue(null, data.access);
        originalRequest.headers.Authorization = `Bearer ${data.access}`;
        return api(originalRequest);
      } catch (refreshError) {
        if (isRemovedError(refreshError)) {
          flushQueue(refreshError, null);
          redirectRemoved();
          return Promise.reject(refreshError);
        }
        flushQueue(refreshError, null);
        clearTokens();
        window.location.href = "/login";
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;
