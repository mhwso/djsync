// Kleiner Helfer zum Bauen von DOM-Elementen ohne innerHTML (Daten werden nie als HTML gelesen).
//
//   h("p", { class: "muted" }, "Text", h("strong", {}, "fett"))
//   Attribute mit "on…" werden als Event-Handler gesetzt, false/null/undefined weggelassen.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === false || value == null) continue;
    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      el.setAttribute(key, value === true ? "" : String(value));
    }
  }
  for (const child of children.flat()) {
    if (child === false || child == null) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}
