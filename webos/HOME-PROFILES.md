# Optional Home profiles

A deployment may supply `window.OMARCHY_DATA.homeProfile` before `app.js` starts. No profile means the existing factory behavior. The optional ES5 reader performs no I/O or device configuration.

```json
{
  "schema": 1,
  "apps": [
    {"id": "player", "name": "Local Player", "appId": "org.example.player", "brand": "plex"}
  ],
  "inputs": [
    {"id": "input-one", "name": "Input One", "appId": "com.example.input1"}
  ],
  "defaults": {
    "randomTheme": false,
    "randomWallpaper": false,
    "tvApps": false,
    "widgets": {"weather": false}
  },
  "terminalSummary": "apps 1 local entry"
}
```

## Contract

- `apps` and `inputs` are authored **fallback** catalogs, not claims of hardware discovery. Duplicate, malformed or empty catalogs are ignored as a whole. App IDs are bounded identifiers, not shell commands or URLs.
- App tiles inherit the matching built-in ID/brand's appearance. Optional `bg`/`fg` overrides must be six-digit hex; profile labels are sanitized. Real Tizen app/source adapters retain their existing precedence.
- Existing webOS installed-app discovery still applies when enabled. A profile using only its authored fallback catalog should default `tvApps` to false. A user's saved value still wins.
- `defaults` only accepts known factory-setting keys with matching value types. Widget defaults are merged by known widget name. Unknown/prototype keys are ignored.
- Saved user settings override profile defaults. A profile does not reset existing localStorage or force a new theme.
- `terminalSummary` replaces the demo network/uptime lines with plain text. The current theme and actual source app version are shown automatically. It does not fabricate runtime telemetry or start polling.
- The reader does not install apps, change inputs, enable root/startup integration, open ports, configure SSH, or change platform permissions.

Keep device profiles, account/host details, personal assets, build outputs and recovery material outside published source. This interface is deliberately optional so reusable source fixes remain independent from operator configuration.

Tests:

```sh
node --test webos/tests/*.test.js
```

`--[ Pi :: gpt-6.1-sol ]--`\
   `--- on behalf of:` @OldJobobo
