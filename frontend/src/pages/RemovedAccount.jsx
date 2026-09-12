import { useEffect, useState } from "react";
import { ShieldOff, Mail } from "lucide-react";
import { API_BASE } from "../api/axios";

export default function RemovedAccount() {
  const [contact, setContact] = useState({ email: "", name: "Admin" });

  useEffect(() => {
    fetch(`${API_BASE}/contact-admin/`)
      .then((r) => r.json())
      .then((data) => setContact({ email: data.email || "", name: data.name || "Admin" }))
      .catch(() => {});
  }, []);

  const mailto = contact.email
    ? `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(contact.email)}&su=${encodeURIComponent(
        "DSA Tracker access request"
      )}`
    : null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-rose-50 via-white to-slate-100 px-4">
      <div className="w-full max-w-md card p-8 text-center">
        <div className="mx-auto h-14 w-14 rounded-2xl bg-rose-100 flex items-center justify-center mb-4">
          <ShieldOff className="h-7 w-7 text-rose-600" />
        </div>
        <h1 className="text-xl font-bold text-slate-900 tracking-wide">YOU HAVE BEEN REMOVED FROM THIS WEBSITE</h1>
        <p className="text-sm text-slate-600 mt-3">
          Your credentials are no longer valid for accessing this application.
        </p>
        {mailto ? (
          <a href={mailto} target="_blank" rel="noreferrer" className="btn btn-primary w-full mt-6">
            <Mail className="h-4 w-4" /> Contact Admin
          </a>
        ) : (
          <p className="text-sm text-slate-500 mt-6">Contact the site administrator to request access.</p>
        )}
      </div>
    </div>
  );
}
