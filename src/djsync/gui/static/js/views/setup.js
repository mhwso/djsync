// Einrichtung: Spotify-App anlegen, Client-ID eingeben, im System-Browser bei Spotify anmelden.
// Erscheint beim Start automatisch, wenn Client-ID oder Anmeldung fehlen (siehe app.js),
// und lässt sich jederzeit über die Kopfzeile erneut aufrufen (z. B. nach abgelaufener Anmeldung).
//
// Die Schritte stehen in STEPS. Ein weiterer Schritt (z. B. Anmeldung im eingebetteten
// Spotify-Player) ist ein weiteres Objekt { id, title, done(status), render(ctx) }.

import { api, errorMessage, on } from "../api.js";
import { h } from "../dom.js";

// Gleiche Prüfung wie in Python (config.is_valid_client_id), hier nur für sofortige Rückmeldung
const CLIENT_ID_RE = /^[0-9a-f]{32}$/;

function copyButton(text) {
  const button = h("button", { class: "button", type: "button" }, "Kopieren");
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Kopiert";
    } catch {
      button.textContent = "Bitte von Hand kopieren";
    }
    setTimeout(() => (button.textContent = "Kopieren"), 2000);
  });
  return button;
}

const dashboardStep = {
  id: "dashboard",
  title: "Spotify-App anlegen",
  done: (status) => status.client_id,
  render({ status }) {
    return h(
      "div",
      {},
      h(
        "p",
        {},
        "djsync braucht Zugriff auf deine Spotify-Playlists. Dafür legst du im Spotify-Developer-Dashboard " +
          "einmalig eine kleine „App“ an. Voraussetzung: Spotify Premium.",
      ),
      h(
        "ol",
        { class: "setup-instructions" },
        h(
          "li",
          {},
          "Öffne das ",
          h("a", { href: status.dashboard_url, target: "_blank" }, "Spotify-Developer-Dashboard"),
          " und melde dich mit deinem Spotify-Konto an.",
        ),
        h(
          "li",
          {},
          "Klicke auf ",
          h("strong", {}, "Create app"),
          " und trage ein: App name ",
          h("strong", {}, "djsync"),
          ", Description ",
          h("strong", {}, "Playlists aus Musikordnern"),
          " und als Redirect URI genau diese Adresse (dann „Add“):",
          h(
            "div",
            { class: "setup-copy" },
            h("code", { class: "mono", id: "setup-redirect-uri" }, status.redirect_uri),
            copyButton(status.redirect_uri),
          ),
        ),
        h(
          "li",
          {},
          "Bei „Which API/SDKs are you planning to use?“ ",
          h("strong", {}, "Web API"),
          " anhaken, den Bedingungen zustimmen und ",
          h("strong", {}, "Save"),
          " klicken.",
        ),
        h(
          "li",
          {},
          "In der App auf ",
          h("strong", {}, "Settings"),
          " gehen und die ",
          h("strong", {}, "Client ID"),
          " kopieren. Ein „Client secret“ wird nicht gebraucht.",
        ),
      ),
    );
  },
};

const clientIdStep = {
  id: "client-id",
  title: "Client-ID eingeben",
  done: (status) => status.client_id,
  render({ status, refresh }) {
    const input = h("input", {
      class: "input mono",
      id: "setup-client-id",
      type: "text",
      autocomplete: "off",
      spellcheck: "false",
      placeholder: status.client_id ? "Neue Client-ID (32 Zeichen)" : "32 Zeichen, z. B. 3f2a…",
      "aria-describedby": "setup-client-id-hint",
    });
    const hint = h("p", { class: "setup-hint muted", id: "setup-client-id-hint" });
    const save = h("button", { class: "button primary", type: "submit", disabled: true }, "Speichern");

    function check() {
      const value = input.value.trim().toLowerCase();
      const valid = CLIENT_ID_RE.test(value);
      save.disabled = !valid;
      hint.className = "setup-hint " + (value && !valid ? "error" : "muted");
      hint.textContent = !value
        ? status.client_id
          ? "Eine Client-ID ist bereits gespeichert. Nur ausfüllen, um sie zu ersetzen."
          : "Die Client-ID besteht aus 32 Zeichen aus 0–9 und a–f."
        : valid
          ? "Sieht gut aus."
          : `Das sieht nicht nach einer Client ID aus (${value.length} von 32 Zeichen, nur 0–9 und a–f).`;
    }

    async function submit(event) {
      event.preventDefault();
      save.disabled = true;
      try {
        await api("setup.save_client_id", input.value);
        await refresh();
      } catch (err) {
        hint.className = "setup-hint error";
        hint.textContent = errorMessage(err);
        save.disabled = false;
      }
    }

    input.addEventListener("input", check);
    check();
    return h(
      "form",
      { onsubmit: submit },
      h("label", { for: "setup-client-id" }, "Client ID"),
      h("div", { class: "setup-row" }, input, save),
      hint,
    );
  },
};

const loginStep = {
  id: "login",
  title: "Bei Spotify anmelden",
  done: (status) => status.logged_in,
  render({ status, refresh, cleanups }) {
    const box = h("div", { class: "setup-login" });

    function show(login, url) {
      const parts = [];
      if (!status.client_id) {
        parts.push(h("p", { class: "muted" }, "Zuerst die Client-ID speichern."));
      } else if (login.state === "waiting") {
        parts.push(
          h("p", {}, "Im Browser hat sich die Spotify-Anmeldung geöffnet. Bitte dort den Zugriff bestätigen."),
          url && h("p", { class: "muted" }, "Falls sich nichts geöffnet hat, diese Adresse im Browser aufrufen:"),
          url && h("div", { class: "setup-copy" }, h("code", { class: "mono setup-url" }, url), copyButton(url)),
          h("div", { class: "setup-row" }, h("span", { class: "spinner", "aria-hidden": "true" }), "Warte auf die Bestätigung …",
            h("button", { class: "button", type: "button", onclick: () => api("setup.cancel_login") }, "Abbrechen")),
        );
      } else {
        if (login.state === "success") parts.push(h("p", { class: "notice ok" }, "Anmeldung abgeschlossen."));
        if (login.state === "error") parts.push(h("p", { class: "notice error" }, login.message));
        if (login.state === "cancelled") parts.push(h("p", { class: "muted" }, "Anmeldung abgebrochen."));
        parts.push(
          h("p", {}, status.logged_in
            ? "Du bist angemeldet. Bei abgelaufener Anmeldung oder Problemen kannst du dich hier erneut anmelden."
            : "Die Anmeldung öffnet sich in deinem normalen Browser. Dort kannst du gespeicherte Zugangsdaten und die Zwei-Faktor-Anmeldung nutzen."),
          h("button", { class: "button" + (status.logged_in ? "" : " primary"), type: "button", onclick: start },
            status.logged_in ? "Erneut anmelden" : "Im Browser anmelden"),
        );
      }
      box.replaceChildren(...parts.filter(Boolean));
    }

    async function start() {
      try {
        const { url } = await api("setup.start_login");
        show({ state: "waiting" }, url);
      } catch (err) {
        show({ state: "error", message: errorMessage(err) });
      }
    }

    cleanups.push(on("setup.login", () => refresh()));
    show(status.login);
    return box;
  },
};

// Reihenfolge der Schritte; weitere Schritte hier ergänzen
export const STEPS = [dashboardStep, clientIdStep, loginStep];

export default {
  title: "Einrichtung",

  async render(root, _params, { navigate }) {
    const body = h("div", { class: "view-body" }, h("p", { class: "muted" }, "Lade Einrichtung …"));
    root.append(h("div", { class: "view-head" }, h("h1", {}, "Einrichtung")), body);
    const cleanups = [];

    async function refresh() {
      let status;
      try {
        status = await api("setup.status");
      } catch (err) {
        body.replaceChildren(h("p", { class: "notice error" }, errorMessage(err)));
        return;
      }
      cleanups.splice(0).forEach((off) => off());
      const ctx = { status, refresh, cleanups };
      const current = STEPS.find((step) => !step.done(status));
      body.replaceChildren(
        h(
          "ol",
          { class: "setup-steps" },
          STEPS.map((step, i) =>
            h(
              "li",
              { class: "setup-step" + (step.done(status) ? " done" : "") + (step === current ? " current" : "") },
              h(
                "div",
                { class: "setup-step-head" },
                h("span", { class: "setup-step-number", "aria-hidden": "true" }, step.done(status) ? "✓" : String(i + 1)),
                h("h2", {}, step.title),
                step.done(status) && h("span", { class: "badge ok" }, "Erledigt"),
              ),
              h("div", { class: "setup-step-body" }, step.render(ctx)),
            ),
          ),
        ),
        h(
          "div",
          { class: "setup-footer" },
          status.needed
            ? h("p", { class: "muted" }, "Sobald alle Schritte erledigt sind, geht es zu deinen Ordnern.")
            : h("button", { class: "button primary", type: "button", onclick: () => navigate("folders") }, "Weiter zu den Ordnern"),
        ),
      );
    }

    await refresh();
    return () => cleanups.forEach((off) => off());
  },
};
