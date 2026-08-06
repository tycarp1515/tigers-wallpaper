# Sports Schedule Wallpapers — Auto-Updating

Renders schedule wallpapers that update themselves every morning.
**GitHub runs everything — your computer never has to be on.**

Produces four things:

| Output | What it is |
|---|---|
| `output/current.png` | Detroit Tigers — current month, iPhone wallpaper |
| `output/michigan.png` | Michigan Football — full 2026 season, iPhone wallpaper |
| `output/widget-next.png` | Tigers medium widget — next 4 games |
| `output/widget-<month>.png` | Tigers large widget — one per month |

Data comes from MLB's Stats API and ESPN's public API. No keys, no accounts, no cost.

---

## How it works

```
   GitHub Actions (5x daily)
        |-- fetch Tigers schedule + scores from MLB
        |-- fetch Michigan schedule, scores, ranks, TV from ESPN
        |-- render the PNGs
        |-- commit them back to this repo
        v
   raw.githubusercontent.com/<you>/tigers-wallpaper/main/output/<file>.png
        |
        +--> iPhone Shortcut  -> sets your wallpaper
        +--> Scriptable widget -> home screen (refreshes on its own)
```

---

## Setup

Everything below is done in a browser. No Python or Git needed locally.

### 1. Upload the files

In your `tigers-wallpaper` repo: **Add file → Upload files**, then drag in
everything from this folder *except* the `output` folder (it gets created
automatically). Commit.

Your repo root should end up with:

```
.github/workflows/daily.yml
assets/fonts/
assets/logos/          <- 30 MLB team logos
assets/cfb-logos/      <- just MICH.png (the official block M)
render_wallpaper.py
render_widgets.py
render_michigan.py
requirements.txt
Tigers-Widget.js
.gitignore
README.md
```

Click into `.github` afterward and confirm you can reach `workflows/daily.yml`.
If a browser drag flattened it, use **Add file → Create new file** and type the
full path `.github/workflows/daily.yml` — the slashes rebuild the folders.

### 2. Run it once

**Actions** tab → **Daily Tigers wallpaper** → **Run workflow** → **Run workflow**.

Wait about a minute and refresh. Green check = working. Click into the run to
read the log — the Michigan step prints every game it parsed, which is the
fastest way to spot a problem.

### 3. Grab your URLs

Swap in your GitHub username:

```
https://raw.githubusercontent.com/YOU/tigers-wallpaper/main/output/current.png
https://raw.githubusercontent.com/YOU/tigers-wallpaper/main/output/michigan.png
https://raw.githubusercontent.com/YOU/tigers-wallpaper/main/output/widget-next.png
```

Open each in a browser to confirm the image loads by itself on a blank page.

### 4. iPhone Shortcut (wallpaper)

1. **Shortcuts** → **+** → add two actions, in this order:
   - **Get Contents of URL** — paste one of the URLs above
   - **Set Wallpaper** — tap its input, choose **Contents of URL**
2. Set it to **Lock Screen** only. *(Targeting Lock + Home rebuilds the iOS
   wallpaper pair, which resets your home screen to a solid colour and wipes
   your app icon appearance setting.)*
3. Name it, tap once to test, allow the network prompt.
4. **Automation** tab → **+** → **App** → pick an app you open every morning →
   your shortcut → **Run Immediately**.

   A *Time of Day* trigger also works, but iOS often won't complete a wallpaper
   change while the phone is locked. An app trigger guarantees it's unlocked.

To mirror it onto the home screen: **Settings → Wallpaper → Customize**
(Home Screen) → **Pair**, and turn **Blur off**.

### 5. Scriptable widget (optional)

1. Install **Scriptable** (free, App Store)
2. **+** → paste in `Tigers-Widget.js` → rename it *Tigers Widget*
3. Long-press home screen → **+** → **Scriptable** → **Medium** → Add Widget
4. Tap the widget → **Edit Widget** → Script = *Tigers Widget*, Parameter = blank

For more pages, add more widgets and set the **Parameter** field:

| Parameter | Shows | Widget size |
|---|---|---|
| *(blank)* | next 4 games | Medium |
| `month` | month currently in play | Large |
| `july`, `august`, `september` | that specific month | Large |

Drag one onto another to make a swipeable stack.

Widgets refresh in the background on their own — no automation needed.

---

## Notes

**Timing.** GitHub's scheduled jobs run late under load — sometimes by hours.
That's why the workflow fires five times a day (4:40, 6:40, 8:40, 10:40 AM and
12:40 PM ET) instead of once. It only commits when an image actually changed.

**Swapping a logo.** Drop a transparent PNG into `assets/logos/` (Tigers, named
by abbreviation like `CLE.png`) or `assets/cfb-logos/` (Michigan, named by
abbreviation or ESPN team id). Bundled files always beat the auto-downloaded
version. Delete one to go back to the automatic logo.

**Michigan opponent logos** download from ESPN at 500px and cache themselves in
`assets/cfb-logos/` on the first run.

**Troubleshooting Michigan.** If the ESPN data looks wrong, the Actions log
prints each parsed game. For the full payload, change the Michigan step in
`daily.yml` to `run: DEBUG_ESPN=1 python render_michigan.py`.

**Workflow paused?** GitHub suspends scheduled workflows after 60 days of repo
inactivity. Open **Actions** and click **Enable workflow**.

**Changing update times.** Edit the `cron` lines in
`.github/workflows/daily.yml`. They're UTC — ET is UTC−4 in summer, UTC−5 in
winter.

**Season year.** Both scripts default to the current calendar year. Override with
the `TIGERS_SEASON` / `MICH_SEASON` environment variables.
