/** Pull a readable message out of DRF / network errors. */
export function formatApiError(err, fallback = "Something went wrong.") {
  if (!err?.response) {
    return "Cannot reach the server. Make sure the backend is running.";
  }
  const data = err.response.data;
  if (!data) return fallback;
  if (typeof data === "string") {
    const trimmed = data.trim();
    return trimmed && !trimmed.startsWith("<") ? trimmed.slice(0, 280) : fallback;
  }
  if (data.message) {
    return Array.isArray(data.message) ? String(data.message[0]) : String(data.message);
  }
  if (data.detail) {
    return Array.isArray(data.detail) ? String(data.detail[0]) : String(data.detail);
  }
  const messages = [];
  for (const [field, value] of Object.entries(data)) {
    const label = field === "non_field_errors" || field === "linkedin_post_url" ? "" : `${field}: `;
    if (Array.isArray(value)) {
      value.forEach((v) => messages.push(`${label}${v}`));
    } else if (typeof value === "string") {
      messages.push(`${label}${value}`);
    }
  }
  return messages.length ? messages.join(" ") : fallback;
}
