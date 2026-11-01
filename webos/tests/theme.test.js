// node --test webos/tests/theme.test.js — semantic equivalence, not palette recoloring.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const Theme = require("../app/theme.js");
const app = path.join(__dirname, "../app");
const ctx = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(app, "data.js"), "utf8"), ctx);
const palettes = JSON.parse(JSON.stringify(ctx.window.OMARCHY_DATA.themes));

// Distinct values expose swapped roles and precedence mistakes. Short names are
// the semantic aliases supported by Omarchy's colors.toml resolver, not ANSI hue guesses.
const semantic = {
  bg: "#222222", lighter_bg: "#242d1d", dark_bg: "#151515", darker_bg: "#101010",
  fg: "#c2c2b0", dark_fg: "#666666", light_fg: "#aaaaaa", bright_fg: "#d7c483",
  accent: "#78824b", active_border_color: "#c9a554", muted: "#8a8a7e",
  selection: "#383838", selection_background: "#313829", selection_foreground: "#dedcb1",
  red: "#685742", green: "#5f875f", yellow: "#b36d43", blue: "#445566",
  magenta: "#bb7744", bright_magenta: "#cc8855", cyan: "#c9a554"
};

function checkSemantic(r, p) {
  for (const [role, key] of Object.entries({bg:"bg",bgAlt:"lighter_bg",bgDark:"dark_bg",bgDeep:"darker_bg",
    fg:"fg",fgBright:"bright_fg",fgDim:"dark_fg",muted:"muted",accent:"accent",focus:"active_border_color",
    selection:"selection_background",selectionFg:"selection_foreground",green:"green",yellow:"yellow",
    red:"red",cyan:"cyan",magenta:"magenta",accent2:"bright_magenta"}))
    assert.equal(r[role], p[key], role + " must preserve its authored semantic token");
}

test("zero RGB channels, short hex, alpha zero, and invalid input", () => {
  assert.equal(Theme.hexToRgba("#000000", 0.85), "rgba(0,0,0,0.85)");
  assert.equal(Theme.hexToRgba("#00ff00", 0), "rgba(0,255,0,0)");
  assert.equal(Theme.hexToRgba("#f00", 0.5), "rgba(255,0,0,0.5)");
  assert.equal(Theme.hexToRgba("00FFFF", 1), "rgba(0,255,255,1)");
  assert.equal(Theme.hexToRgba("#bad-input", 1), "rgba(26,27,38,1)");
  assert.equal(Theme.hexToRgba(null, NaN), "rgba(26,27,38,1)");
  assert.equal(Theme.hexToRgba("#fff", 2), "rgba(255,255,255,1)");
  assert.equal(Theme.hexToRgba("#000", -1), "rgba(0,0,0,0)");
});

test("short semantic palette maps each role without altering an authored color", () => {
  const p = Object.freeze({...semantic});
  checkSemantic(Theme.resolve(p, "semantic"), p);
});

test("canonical long names win over short aliases and ANSI compatibility slots", () => {
  const aliases = {background:"bg",lighter_background:"lighter_bg",dark_background:"dark_bg",darker_background:"darker_bg",
    foreground:"fg",bright_foreground:"bright_fg",dark_foreground:"dark_fg"};
  const p = {...semantic, color0:"#ff0000",color4:"#00ff00",color7:"#0000ff",color8:"#ff00ff",color15:"#00ffff"};
  for (const [long, short] of Object.entries(aliases)) {p[long]=semantic[short];p[short]="#123456";}
  checkSemantic(Theme.resolve(p, "canonical"), semantic);
  assert.equal(Theme.resolve({...p, accent:"#010203"}).accent, "#010203", "explicit accent is not ANSI blue");
});

test("explicit selection background and foreground stay paired, not mixed with neutral selection", () => {
  const r = Theme.resolve(semantic);
  assert.notEqual(semantic.selection, semantic.selection_background);
  assert.equal(r.selection, semantic.selection_background);
  assert.equal(r.selectionFg, semantic.selection_foreground);
  const fallback = Theme.resolve({background:"#101010",foreground:"#dddddd",selection:"#303030",bright_foreground:"#eeeeee"});
  assert.equal(fallback.selection,"#303030");assert.equal(fallback.selectionFg,"#eeeeee");
});

test("focus border and primary accent are distinct roles when the author says so", () => {
  const r = Theme.resolve(semantic), css = Theme.cssVariables(r, 0.85);
  assert.equal(css["--t-focus"], semantic.active_border_color);
  assert.equal(css["--t-accent"], semantic.accent);
  assert.equal(Theme.resolve({accent:"#123456"}).focus, "#123456");
  assert.equal(Theme.resolve({accent:"#123456",active_border_color:"#000000"}).focus, "#000000");
});

test("ANSI-only palettes retain color0..15 semantics and derive only missing shades", () => {
  const p = Object.fromEntries(Array.from({length:16},(_,i)=>["color"+i,"#"+(0x101010+i*0x080808).toString(16).padStart(6,"0")]));
  const r = Theme.resolve(p,"ansi");
  for (const [role, slot] of Object.entries({bg:0,bgAlt:0,fg:7,fgBright:15,fgDim:8,muted:8,accent:4,focus:4,
    red:1,green:2,yellow:3,magenta:5,cyan:6,accent2:13,selection:8,selectionFg:15})) assert.equal(r[role],p["color"+slot],role);
  assert.equal(r.bgDark,"#0c0c0c");assert.equal(r.bgDeep,"#080808");
});

test("nested ANSI banks mean the same slots; normal white is foreground, not bright white", () => {
  const p={normal:Object.freeze({black:"#101010",white:"#dddddd",blue:"#88aaff",green:"#557755",magenta:"#775577"}),
    bright:Object.freeze({black:"#555555",white:"#ffffff",magenta:"#aa77aa"})};
  const r=Theme.resolve(p,"nested");
  assert.equal(r.bg,"#101010");assert.equal(r.fg,"#dddddd");assert.equal(r.fgBright,"#ffffff");
  assert.equal(r.accent,"#88aaff");assert.equal(r.fgDim,"#555555");assert.equal(r.accent2,"#aa77aa");
  assert.equal(r.selection,"#555555");assert.equal(r.selectionFg,"#ffffff");
});

test("missing roles fall back within the same theme and invalid tokens are skipped", () => {
  const r=Theme.resolve({background:"#ffffff",foreground:"#000000"},"plain");
  assert.equal(r.bgAlt,"#ffffff");assert.equal(r.accent,"#000000");assert.equal(r.accent2,"#000000");
  assert.equal(r.selection,"#ffffff");assert.equal(r.selectionFg,"#000000");assert.equal(r.fgDim,"#000000");
  assert.equal(Theme.resolve({background:"broken",bg:"#000000",accent:"bad",blue:"#003300"}).bg,"#000000");
  assert.equal(Theme.resolve({accent:"bad",blue:"#003300"}).accent,"#003300");
  assert.equal(Theme.resolve({background:"#ffffff"}).fg,"#000000","safe foreground only when none is authored");
  assert.equal(Theme.resolve({purple:"#110033",bright_purple:"#440066"}).magenta,"#110033");
  assert.equal(Theme.resolve({purple:"#110033",bright_purple:"#440066"}).accent2,"#440066");
});

test("low contrast is diagnosable, never a reason to silently change a token", () => {
  const p={background:"#222222",foreground:"#222222",accent:"#222222",selection_background:"#222222",selection_foreground:"#222222",
    dark_foreground:"#222222",bright_foreground:"#222222",red:"#222222",green:"#222222",yellow:"#222222",cyan:"#222222"};
  const r=Theme.resolve(p);
  for(const k of ["fg","fgBright","fgDim","accent","focus","red","green","yellow","cyan","selectionFg"]) assert.equal(r[k],"#222222",k);
  assert.equal(Theme.contrast(r.fg,r.bg),1);
});

test("Miasma focus, headings and status colors are not contrast-adjusted or reassigned", () => {
  const p=palettes.miasma,r=Theme.resolve(p,"miasma"),css=Theme.cssVariables(r,.85);
  assert.equal(css["--t-accent"],"#78824b");assert.equal(r.focus,"#78824b");
  assert.equal(r.fgDim,"#555555");assert.equal(r.green,"#5f875f");assert.equal(r.yellow,"#b36d43");assert.equal(r.red,"#685742");
  assert.equal(r.accent2,"#bb7744","secondary ANSI color remains available, but is not generic heading color");
});

test("bar, panel, popup, scrim and selection use their own surface roles", () => {
  const r=Theme.resolve(semantic),css=Theme.cssVariables(r,.85);
  assert.equal(css["--win-bg"],Theme.hexToRgba(semantic.bg,.85));
  assert.equal(css["--bar-bg"],Theme.hexToRgba(semantic.dark_bg,.88));
  assert.equal(css["--popup-bg"],Theme.hexToRgba(semantic.lighter_bg,.95));
  assert.equal(css["--scrim-bg"],Theme.hexToRgba(semantic.darker_bg,.55));
  assert.equal(css["--t-selection-bg"],semantic.selection_background);assert.equal(css["--t-selection-fg"],semantic.selection_foreground);
});

test("Vantablack remains black instead of inheriting Tokyo Night's RGB channels", () => {
  const css=Theme.cssVariables(Theme.resolve(palettes.vantablack,"vantablack"),.85);
  assert.equal(css["--win-bg"],"rgba(0,0,0,0.85)");
});

for (const [name, palette] of Object.entries(palettes)) {
  test(name + ": authored semantic role values and source data stay unchanged", () => {
    const original=JSON.stringify(palette),r=Theme.resolve(Object.freeze(palette),name);
    for(const [role,key] of Object.entries({bg:"background",bgAlt:"lighter_background",bgDark:"dark_background",bgDeep:"darker_background",
      fg:"foreground",fgBright:"bright_foreground",fgDim:"dark_foreground",muted:"muted",accent:"accent",accent2:"bright_magenta",
      red:"red",green:"green",yellow:"yellow",cyan:"cyan"})) if(palette[key]) assert.equal(r[role],palette[key],role);
    assert.equal(r.selection,palette.selection_background||palette.selection||r.bg);
    assert.equal(r.selectionFg,palette.selection_foreground||r.fgBright);
    assert.equal(r.focus,palette.active_border_color||r.accent);
    assert.equal(JSON.stringify(palette),original);
  });
}

test("legacy CSS fallback preserves exact surface, selection and focus RGB values", () => {
  const html=fs.readFileSync(path.join(app,"index.html"),"utf8");
  const css=html.slice(html.indexOf("<style>")+7,html.indexOf("</style>"));
  for(const [name,p] of [["semantic",semantic],...["miasma","catppuccin","catppuccin-latte","vantablack"].map(n=>[n,palettes[n]])]) {
    const style={textContent:css},timers=[];
    function Declaration() {} Declaration.prototype.setProperty=function() {};
    const body={nodeType:1,style:{display:""},querySelectorAll:()=>[],getAttribute:()=>null};
    const supports={supports:()=>false};
    const context={window:{CSS:supports,fetch(){},addEventListener(){}},CSS:supports,CSSStyleDeclaration:Declaration,
      document:{body,querySelector:()=>style,querySelectorAll:()=>[]},MutationObserver:function(){this.observe=function(){};},setTimeout:f=>timers.push(f)};
    vm.runInNewContext(fs.readFileSync(path.join(app,"compat.js"),"utf8"),context);
    const r=Theme.resolve(p,name),vars=Theme.cssVariables(r,.85),declaration=new Declaration();
    for(const [key,value] of Object.entries(vars)) declaration.setProperty(key,value);
    while(timers.length)timers.shift()();
    assert.ok(!style.textContent.includes("var(--t-"),name+" resolves palette variables");
    assert.ok(style.textContent.includes(".modal-item.focused{background:"+r.selection));
    assert.ok(style.textContent.includes("border-left-color:"+r.focus));
    assert.ok(style.textContent.includes(".tui-ok{color:"+r.green+"}"));
    assert.ok(style.textContent.includes(".tui-err{color:"+r.red+"}"));
    assert.ok(style.textContent.includes(".extra-focused{outline:3px solid "+r.focus));
    assert.ok(style.textContent.includes("#modal-title{font-size:calc(24px * 1);font-weight:700;color:"+r.accent));
    assert.ok(style.textContent.includes("#waybar{position:absolute;top:0;left:0;width:1920px;height:52px;background:"+vars["--bar-bg"]));
  }
});

test("UI consumers use primary accent headings, selection pairs and semantic status colors", () => {
  const html=fs.readFileSync(path.join(app,"index.html"),"utf8");
  assert.ok(html.indexOf('src="theme.js"')<html.indexOf('src="app.js"'));
  assert.equal((html.match(/<style>/g)||[]).length,1,"legacy shim must process all theme-dependent rules");
  for(const selector of ["#term-logo",".win-title","#modal-title"]) {
    const body=html.slice(html.indexOf(selector+" {"),html.indexOf("}",html.indexOf(selector+" {")));
    assert.match(body,/color: var\(--t-accent\)/);assert.doesNotMatch(body,/--t-accent2/);
  }
  assert.match(html,/\.modal-item\.focused\s*\{[^}]*background:\s*var\(--t-selection-bg\)[^}]*color:\s*var\(--t-selection-fg\)[^}]*border-left-color:\s*var\(--t-focus\)/);
  assert.match(html,/\.app-tile\.focused \.tile-themed\s*\{[^}]*color:\s*var\(--t-selection-fg\)/);
  assert.match(html,/\.tui-ok\{color:var\(--t-green\);\}/);assert.match(html,/\.tui-err\{color:var\(--t-red\);\}/);
  assert.ok(!html.includes("--t-accent-text"));
  const src=fs.readFileSync(path.join(app,"app.js"),"utf8");
  assert.match(src,/themeRoleSource !== source/);assert.match(src,/themeRoleName !== cfg\.theme/);
});
