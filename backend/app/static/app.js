"use strict";
const csrf = document.querySelector('meta[name="csrf-token"]').content;
async function api(path, body = {}) {
  const response = await fetch(path, {
    method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
    body: JSON.stringify(body)
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Сервер недоступен. Повторите попытку позже."); }
  if (!response.ok) throw new Error(data.message || "Проверьте данные и повторите попытку");
  return data;
}
function feedback(element, text, ok = false) {
  element.textContent = text;
  element.classList.toggle("success", ok);
  element.classList.toggle("error", !ok);
}
function bindForm(id, action) {
  const form = document.getElementById(id);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]');
    const output = form.querySelector(".feedback");
    button.disabled = true;
    output.textContent = "Проверяем…";
    try { await action(form, output); }
    catch (error) { feedback(output, error.message); }
    finally { if (!form.dataset.done) button.disabled = false; }
  });
}
function locationNow() {
  return new Promise((resolve, reject) => {
    if (!window.isSecureContext) return reject(new Error("Геолокация требует HTTPS или localhost"));
    if (!navigator.geolocation) return reject(new Error("Браузер не поддерживает геолокацию"));
    navigator.geolocation.getCurrentPosition(resolve, () => reject(new Error(
      "Геолокация недоступна. Разрешите доступ к местоположению в настройках браузера."
    )), {enableHighAccuracy: true, timeout: 15000, maximumAge: 0});
  });
}
function fingerprint() {
  return {
    user_agent: navigator.userAgent, language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "unknown",
    screen_width: screen.width, screen_height: screen.height
  };
}
bindForm("join-form", async (form) => {
  const data = await api("/api/sessions/resolve", Object.fromEntries(new FormData(form)));
  location.assign(data.student_url);
});
bindForm("create-form", async (form) => {
  const body = Object.fromEntries(new FormData(form));
  for (const key of ["duration_minutes", "radius"]) body[key] = Number(body[key]);
  const data = await api("/api/sessions", body);
  location.assign(data.teacher_url);
});
bindForm("student-form", async (form, output) => {
  const body = Object.fromEntries(new FormData(form));
  body.fingerprint = fingerprint();
  output.textContent = "Разрешите доступ к местоположению…";
  try {
    const {coords} = await locationNow();
    body.latitude = coords.latitude;
    body.longitude = coords.longitude;
  } catch {
    // Send the attempt anyway, so the teacher sees the reason for rejection.
    body.latitude = null; body.longitude = null;
  }
  const data = await api(`/api/attendance/${form.dataset.code}`, body);
  form.dataset.done = "true";
  feedback(output, data.message + ". Вы отмечены в журнале занятия.", true);
});
const panel = document.querySelector("[data-session]");
if (panel) {
  const id = panel.dataset.session;
  let editing = false;
  const manual = document.getElementById("manual-form");
  if (manual) manual.addEventListener("input", () => { editing = true; });
  bindForm("manual-form", async (form) => {
    await api(`/api/sessions/${id}/manual`, Object.fromEntries(new FormData(form)));
    location.reload();
  });
  const closeButton = document.getElementById("close-session");
  if (closeButton) closeButton.addEventListener("click", async () => {
    if (!confirm("Завершить приём отметок?")) return;
    closeButton.disabled = true;
    try { await api(`/api/sessions/${id}/close`); location.reload(); }
    catch (error) { feedback(document.getElementById("teacher-feedback"), error.message); closeButton.disabled = false; }
  });
  document.getElementById("refresh-journal").addEventListener("click", () => {
    if (!editing || confirm("Обновить страницу и очистить незавершённую ручную отметку?")) location.reload();
  });
  // Do not discard a manual entry or an open disclosure while the teacher works.
  setInterval(() => {
    const manualOpen = manual && manual.closest("details").open;
    if (!document.hidden && !editing && !manualOpen && !document.activeElement.matches("input,button")) location.reload();
  }, 15000);
}
