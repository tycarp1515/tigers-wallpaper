# Tigers Schedule Wallpaper — Fully Automatic

A Detroit Tigers schedule wallpaper (1290×2796) that updates itself every morning
with the latest results. **GitHub runs it — your computer doesn't need to be on.**

Finished games dim and show **W/L** (wins in orange); upcoming games stay bright with
the start time in **ET**. Orange bar = home, white bar = away. Today's game gets an
orange outline. When a month's games are done, it rolls to the next month on its own.

Data comes from MLB's public Stats API. No API key, no account, no cost.

---

## How it works

```
   GitHub Actions (7:00 AM ET daily)
        |
        |-- fetches the Tigers schedule + scores from MLB
        |-- renders the current month's PNG
        |-- commits it to this repo
        v
   https://raw.githubusercontent.com/.../output/current.png
        |
        v
   iPhone Shortcut (7:15 AM) -> sets your wallpaper
```

---

## Setup — all in a browser (~15 min, once)

You do **not** need Python or Git installed. Everything runs on GitHub.

### 1. Create the repo

1. Sign in at https://github.com (a free account is fine).
2. Click **+** (top right) → **New repository**.
3. Name it `tigers-wallpaper`, set it to **Public**, click **Create repository**.
   - Public matters: it's what lets your phone fetch the image without a login.

### 2. Upload these files

1. On the new repo page, click **uploading an existing file**.
2. Drag in **everything from this folder** — `render_wallpaper.py`, `requirements.txt`,
   `.gitignore`, and the `assets` and `.github` folders.
   - Dragging a folder brings its contents along, including `.github/workflows/daily.yml`.
     That file is the scheduler — without it, nothing runs automatically.
3. Click **Commit changes**.

### 3. Turn the scheduler on and test it

1. Go to the **Actions** tab. If it asks you to enable workflows, click the green button.
2. Click **Daily Tigers wallpaper** in the left sidebar → **Run workflow** → **Run workflow**.
3. Wait about a minute, then refresh. A green check means it worked.
   - If it fails, click into the run to see the log and send me what it says.

### 4. Confirm the image exists

Open this in a browser (swap in your username):

```
https://raw.githubusercontent.com/YOUR-USERNAME/tigers-wallpaper/main/output/current.png
```

You should see the wallpaper. **Copy this URL — the phone needs it.**

From here on GitHub re-renders it every morning at 7:00 AM ET. Nothing else to do
on a computer, ever.

### 5. The iPhone Shortcut

1. Open **Shortcuts** → **+** → add two actions in this order:
   - **Get Contents of URL** — paste the raw URL from step 4.
   - **Set Wallpaper** — set its input to the output of *Get Contents of URL*.
     Turn **off** "Show Preview" so it applies without a tap.
2. Name it `Tigers Wallpaper`, then tap it once to test. Your lock screen should change.
3. **Automation** tab → **+** → **Time of Day** → **7:15 AM** → **Daily** →
   choose the shortcut → set it to **Run Immediately**, and turn off
   **Notify When Run** if you don't want a daily banner.

---

## What "fully automatic" really means

The rendering side is 100% hands-off: GitHub is always on, so the image refreshes every
morning whether your PC, your phone, or anything else is awake.

The one piece Apple controls is *applying* the image. iOS has gone back and forth on
whether a Set Wallpaper automation may run silently. If yours insists on a confirmation
tap, that's an iOS restriction rather than a broken setup — the fresh image is waiting
either way, and you can run the Shortcut manually anytime.

---

## Maintenance

Essentially none. Two things worth knowing:

- **GitHub pauses scheduled workflows after 60 days of repo inactivity.** Daily commits
  usually count as activity, but if updates ever stop, open the **Actions** tab and click
  **Enable workflow**. Five seconds.
- **To change the update time**, edit `.github/workflows/daily.yml` and adjust the
  `cron` line. It's in UTC: `0 11 * * *` is 7:00 AM Eastern during daylight saving.

---

## Files

| File | What it does |
|------|--------------|
| `.github/workflows/daily.yml` | The scheduler. Runs the renderer daily on GitHub. |
| `render_wallpaper.py` | Fetches the schedule and draws the PNG. |
| `requirements.txt` | Python packages GitHub installs automatically. |
| `assets/logos/` | All 30 team logos, transparent. |
| `assets/fonts/` | The typefaces used. |
| `output/current.png` | The live wallpaper. This is what your phone pulls. |

### Swapping a logo
Drop a transparent PNG named for the team's abbreviation (`CLE.png`, `NYY.png`, …)
into `assets/logos/` on GitHub. The next run picks it up.

### Forcing a season
The script defaults to the current calendar year. To pin one, set the environment
variable `TIGERS_SEASON`.
