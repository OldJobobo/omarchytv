/* Semantic palette roles for the shared webOS/Tizen UI. No DOM, timers, or dependencies.
 * Keep this ES5: webOS 3.x uses Chromium 38. Never recolor an authored role.
 * Long/short names and ANSI fallbacks follow Omarchy's omarchy-theme-color resolver;
 * nested normal/bright banks are the existing TV format for the same ANSI slots.
 * This consumes palette data, not desktop shell.toml surface overrides. */
(function (root) {
  "use strict";

  function rgb(hex) {
    if (typeof hex !== "string") return null;
    var h = hex.replace(/^#/, "");
    if (!/^(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(h)) return null;
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }

  function pick(values, fallback) {
    for (var i = 0; i < values.length; i++)
      if (typeof values[i] === "string" && values[i].charAt(0) === "#" && rgb(values[i])) return values[i];
    return fallback;
  }

  function opacity(value, fallback) {
    return typeof value === "number" && isFinite(value) ? Math.max(0, Math.min(1, value)) : fallback;
  }

  function hexToRgba(hex, alpha) {
    var c = rgb(hex) || rgb("#1a1b26");
    // Zero channels (and zero opacity) are valid, not missing values.
    return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + opacity(alpha, 1) + ")";
  }

  function luminance(hex) {
    var c = rgb(hex) || [0, 0, 0], out = [];
    for (var i = 0; i < 3; i++) {
      var v = c[i] / 255;
      out[i] = v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    return out[0] * 0.2126 + out[1] * 0.7152 + out[2] * 0.0722;
  }

  // Diagnostics/missing-foreground fallback only; never recolor an authored token.
  function contrast(a, b) {
    var x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }

  // Derive only missing shade/bright fallbacks, as Omarchy does. Never mix an authored token.
  function mix(a, b, amount) {
    var x = rgb(a), y = rgb(b), out = "#";
    for (var i = 0; i < 3; i++) {
      var channel = Math.round(x[i] + (y[i] - x[i]) * amount).toString(16);
      out += channel.length === 1 ? "0" + channel : channel;
    }
    return out;
  }

  function resolve(palette, name) {
    var t = palette || {}, n = t.normal || {}, b = t.bright || {};
    var bg = pick([t.background, t.bg, t.color0, n.black], "#1a1b26");
    var fg = pick([t.foreground, t.fg, t.color7, n.white, b.white],
      contrast("#ffffff", bg) > contrast("#000000", bg) ? "#ffffff" : "#000000");
    var bright = pick([t.bright_foreground, t.bright_fg, t.color15, b.white], fg);
    var dim = pick([t.dark_foreground, t.dark_fg, t.color8, b.black], fg);
    var accent = pick([t.accent, t.blue, t.color4, n.blue], fg);
    var magenta = pick([t.magenta, t.color5, n.magenta, t.purple], null);
    return {
      name: name || "tokyo-night",
      bg: bg,
      bgAlt: pick([t.lighter_background, t.lighter_bg], bg),
      bgDark: pick([t.dark_background, t.dark_bg], mix(bg, "#000000", 0.25)),
      bgDeep: pick([t.darker_background, t.darker_bg], mix(bg, "#000000", 0.5)),
      fg: fg, fgBright: bright, fgDim: dim,
      muted: pick([t.muted, t.color8, b.black], dim),
      accent: accent,
      focus: pick([t.active_border_color], accent),
      // Retain the existing secondary ANSI role for categorical/lighting uses,
      // not as a replacement for primary-accent UI headings.
      accent2: pick([t.bright_magenta, t.color13, b.magenta, t.bright_purple], magenta ? mix(magenta, "#ffffff", 0.2) : accent),
      // The explicit selection pair belongs together. `selection` may be a
      // separate neutral ramp slot and must not displace selection_background.
      selection: pick([t.selection_background, t.selection, t.color8, b.black], bg),
      selectionFg: pick([t.selection_foreground, t.selection_fg], bright),
      magenta: magenta || accent,
      green: pick([t.green, t.color2, n.green], fg),
      yellow: pick([t.yellow, t.color3, n.yellow], fg),
      red: pick([t.red, t.color1, n.red], fg),
      cyan: pick([t.cyan, t.color6, n.cyan], fg)
    };
  }

  function cssVariables(t, alpha) {
    var a = opacity(alpha, 0.75);
    return {
      "--t-bg": t.bg, "--t-bg-alt": t.bgAlt,
      "--t-bg-dark": t.bgDark, "--t-bg-deep": t.bgDeep,
      "--t-fg": t.fg, "--t-fg-bright": t.fgBright, "--t-fg-dim": t.fgDim,
      "--t-muted": t.muted, "--t-accent": t.accent, "--t-focus": t.focus,
      "--t-accent2": t.accent2, "--t-selection-bg": t.selection, "--t-selection-fg": t.selectionFg,
      "--t-green": t.green, "--t-yellow": t.yellow, "--t-red": t.red, "--t-cyan": t.cyan,
      "--win-bg": hexToRgba(t.bg, a),
      "--bar-bg": hexToRgba(t.bgDark, Math.min(0.88, a + 0.05)),
      "--popup-bg": hexToRgba(t.bgAlt, 0.95),
      "--scrim-bg": hexToRgba(t.bgDeep, 0.55)
    };
  }

  var api = { resolve: resolve, cssVariables: cssVariables, hexToRgba: hexToRgba, contrast: contrast };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.OmarchyTheme = api;
})(typeof window !== "undefined" ? window : this);
