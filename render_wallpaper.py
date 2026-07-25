#!/usr/bin/env python3
"""
Detroit Tigers schedule wallpaper — auto-rendered from the live MLB Stats API.

Produces a 1290x2796 PNG for the "active" month (the current month while games
remain, otherwise the next month with games) and writes it to output/current.png.

No API key required. Data source: https://statsapi.mlb.com  (public).
Requires: pillow, requests   ->   pip install pillow requests
"""

import os, sys, math, datetime as dt
from zoneinfo import ZoneInfo
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# --------------------------------------------------------------------- config
HERE      = os.path.dirname(os.path.abspath(__file__))
ASSETS    = os.path.join(HERE, "assets")
LOGOS     = os.path.join(ASSETS, "logos")
FONTS     = os.path.join(ASSETS, "fonts")
OUTDIR    = os.path.join(HERE, "output")
TEAM_ID   = 116                       # Detroit Tigers
SEASON    = int(os.environ.get("TIGERS_SEASON", dt.date.today().year))
ET        = ZoneInfo("America/New_York")

W, H = 1290, 2796
NAVY, ORANGE, WHITE = (12, 35, 64), (250, 70, 22), (255, 255, 255)

# MLB StatsAPI team-id -> our logo file stem
ABBR = {
    109:"AZ",144:"ATL",110:"BAL",111:"BOS",112:"CHC",145:"CWS",113:"CIN",
    114:"CLE",115:"COL",116:"DET",117:"HOU",118:"KC",108:"LAA",119:"LAD",
    146:"MIA",158:"MIL",142:"MIN",121:"NYM",147:"NYY",133:"ATH",143:"PHI",
    134:"PIT",135:"SD",137:"SF",136:"SEA",138:"STL",139:"TB",140:"TEX",
    141:"TOR",120:"WSH",
}

def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)

def logo(stem):
    return Image.open(os.path.join(LOGOS, f"{stem}.png")).convert("RGBA")

# ------------------------------------------------------------------- MLB fetch
def fetch_games(season):
    """Return every Tigers regular-season game as a normalized dict list."""
    url = ("https://statsapi.mlb.com/api/v1/schedule"
           f"?sportId=1&teamId={TEAM_ID}&season={season}"
           "&gameType=R&hydrate=team,linescore")
    data = requests.get(url, timeout=30).json()
    out = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            home = g["teams"]["home"]["team"]["id"]
            away = g["teams"]["away"]["team"]["id"]
            is_home = home == TEAM_ID
            opp_id = away if is_home else home
            start = dt.datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00")).astimezone(ET)
            state = g["status"]["abstractGameState"]           # Preview / Live / Final
            us    = g["teams"]["home" if is_home else "away"]
            them  = g["teams"]["away" if is_home else "home"]
            res = None
            if state == "Final":
                a, b = us.get("score"), them.get("score")
                if a is not None and b is not None:
                    res = "W" if a > b else ("L" if a < b else "T")
            out.append({
                "date": start.date(),
                "day": start.day,
                "month": start.month,
                "time": start.strftime("%-I:%M"),
                "opp": ABBR.get(opp_id, "?"),
                "home": is_home,
                "state": state,
                "res": res,
            })
    return out

def pick_month(games):
    """Render the month containing the next game still to be played.
    Once a month's games are all done, this rolls forward on its own.
    After the final game of the season, it holds on the last month."""
    today = dt.date.today()
    upcoming = sorted(g["date"] for g in games if g["date"] >= today)
    if upcoming:
        d = upcoming[0]
        return d.year, d.month
    last = max(g["date"] for g in games)
    return last.year, last.month

# ---------------------------------------------------------------------- render
def fade(im, a):
    if a >= 255:
        return im
    o = im.copy(); o.putalpha(o.getchannel("A").point(lambda v: int(v * a / 255))); return o

def fit(im, bw, bh):
    s = min(bw / im.width, bh / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)

def backdrop(det):
    bg = Image.new("RGB", (W, H), (4, 5, 8)); px = bg.load()
    cx, cy = W * 0.5, H * 0.84
    for y in range(H):
        for x in range(0, W, 2):
            g = max(0.0, 1.0 - math.hypot((x-cx)/(W*1.02), (y-cy)/(H*0.46))) ** 1.75
            o = max(0.0, 1.0 - math.hypot((x-cx)/(W*0.50), (y-H*0.90)/(H*0.14))) ** 2.6
            c = (min(255, int(4 + NAVY[0]*g*3.2 + ORANGE[0]*o*0.20)),
                 min(255, int(5 + NAVY[1]*g*3.2 + ORANGE[1]*o*0.20)),
                 min(255, int(8 + NAVY[2]*g*3.2 + ORANGE[2]*o*0.20)))
            px[x, y] = c
            if x+1 < W: px[x+1, y] = c
    im = bg.filter(ImageFilter.GaussianBlur(3)).convert("RGBA")
    gh = fade(fit(det, 330, 330), 30)
    for gx, gy in [(-105,5),(35,330),(-120,690),(1075,95),(1150,470)]:
        im.alpha_composite(gh, (gx, gy))
    return im

MONTHS = ["","JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE",
          "JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER"]
MARGIN, COLS, CW, RGAP, BOTTOM = 95, 5, 190, 34, 2326
GRID_TOP_MIN = 880      # never let cards ride up into the month/year header
CH_MAX = 330            # cap so a light month doesn't stretch into giant cards
GAP = (W - 2*MARGIN - COLS*CW) // (COLS - 1)

def build(year, month, games):
    det = logo("DET")
    img = backdrop(det)
    draw = ImageDraw.Draw(img)
    today = dt.date.today()

    label = MONTHS[month]
    size = 250 if len(label) <= 8 else (210 if len(label) <= 9 else 186)
    mf = font("BigShoulders-Bold.ttf", size)
    bb = draw.textbbox((0,0), label, font=mf)
    draw.text(((W-(bb[2]-bb[0]))//2 - bb[0], 560 if size<250 else 545), label,
              font=mf, fill=(0,0,0,0), stroke_width=5, stroke_fill=(255,255,255,125))
    yf = font("GeistMono-Bold.ttf", 44)
    ytxt = " ".join(str(year))
    bb = draw.textbbox((0,0), ytxt, font=yf)
    draw.text(((W-(bb[2]-bb[0]))//2 - bb[0], 792), ytxt, font=yf, fill=ORANGE+(210,))

    month_games = [g for g in games if g["month"] == month and g["date"].year == year]
    month_games.sort(key=lambda g: (g["date"], g["time"]))
    n = len(month_games)
    rows = max(1, math.ceil(n / COLS))
    # Fit the grid between the header and the hero logo, capping card height so
    # a light month (few games) doesn't stretch into giant cards.
    AVAIL = BOTTOM - GRID_TOP_MIN
    CH = min(CH_MAX, (AVAIL - (rows - 1) * RGAP) // rows)
    TOP = BOTTOM - (rows * CH + (rows - 1) * RGAP)

    day_f  = font("BigShoulders-Bold.ttf", 74)
    time_f = font("GeistMono-Regular.ttf", 29)
    res_f  = font("GeistMono-Bold.ttf", 36)

    cards = Image.new("RGBA", (W, H), (0,0,0,0))
    cd = ImageDraw.Draw(cards)
    for i, g in enumerate(month_games):
        r, c = divmod(i, COLS)
        x, y = MARGIN + c*(CW+GAP), TOP + r*(CH+RGAP)
        done = g["state"] == "Final"
        a = 128 if done else 255
        cd.rectangle([x, y, x+CW, y+CH], outline=(255,255,255,int(a*0.58)), width=2)
        cd.text((x+15, y+2), str(g["day"]), font=day_f, fill=(255,255,255,a))
        if done and g["res"]:
            txt, f = g["res"], res_f
        else:
            txt, f = g["time"], time_f
        bb = cd.textbbox((0,0), txt, font=f)
        cd.text((x+CW-15-(bb[2]-bb[0])-bb[0], y+20), txt, font=f,
                fill=(ORANGE+(240,)) if g["res"]=="W" else (255,255,255,a))
        lh = CH - 86 - 48
        lg = fade(fit(logo(g["opp"]), 130, lh), a)
        cards.alpha_composite(lg, (x+(CW-lg.width)//2, y+86+(lh-lg.height)//2))
        cd.rectangle([x+16, y+CH-27, x+CW-16, y+CH-16],
                     fill=(ORANGE if g["home"] else WHITE)+(a,))
        if g["date"] == today:
            cd.rectangle([x-5, y-5, x+CW+5, y+CH+5], outline=ORANGE+(240,), width=3)
    img = Image.alpha_composite(img, cards)

    lf = font("GeistMono-Regular.ttf", 24)
    lab = "A L L   T I M E S   E T"
    bb = ImageDraw.Draw(img).textbbox((0,0), lab, font=lf)
    ImageDraw.Draw(img).text(((W-(bb[2]-bb[0]))//2 - bb[0], 2350), lab,
                             font=lf, fill=(255,255,255,105))

    hero = fit(det, 356, 400)
    hx, hy = (W-hero.width)//2, 2396
    glow = Image.new("RGBA", (W, H), (0,0,0,0))
    gg = Image.new("RGBA", hero.size, (255,120,45,0))
    gg.putalpha(hero.getchannel("A").point(lambda v: int(v*0.55)))
    glow.alpha_composite(gg, (hx, hy))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(34)))
    img.alpha_composite(hero, (hx, hy))
    return img.convert("RGB")

# ------------------------------------------------------------------------ main
def main():
    os.makedirs(OUTDIR, exist_ok=True)
    try:
        games = fetch_games(SEASON)
    except Exception as e:
        print("ERROR fetching schedule:", e, file=sys.stderr)
        sys.exit(1)
    if not games:
        print("No games returned — is the season set correctly?", file=sys.stderr)
        sys.exit(1)
    year, month = pick_month(games)
    img = build(year, month, games)
    cur = os.path.join(OUTDIR, "current.png")
    img.save(cur)
    img.save(os.path.join(OUTDIR, f"Tigers-{MONTHS[month].title()}-{year}.png"))
    print(f"Rendered {MONTHS[month].title()} {year} "
          f"({sum(1 for g in games if g['month']==month and g['date'].year==year)} games) -> {cur}")

if __name__ == "__main__":
    main()
