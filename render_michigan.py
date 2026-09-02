#!/usr/bin/env python3
"""
Michigan Football schedule wallpaper (1290x2796), rendered from the CollegeFootballData API.

Shows every game on one page with: date, opponent logo + AP rank, home/away,
kickoff time (ET) or final score with W/L, and the TV network. Header carries
Michigan's own rank and overall / Big Ten records.

Needs a free CFBD API key in the CFBD_API_KEY environment variable
(get one at https://collegefootballdata.com/key).
Logos are cached in assets/cfb-logos/; drop a PNG there to override one.

    pip install pillow requests
    python render_michigan.py            # normal run
    DEBUG_ESPN=1 python render_michigan.py   # also dump the parsed schedule

Env:
    MICH_SEASON   override season year (default: current year)
"""

import os, sys, math, json, datetime as dt
from zoneinfo import ZoneInfo
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE    = os.path.dirname(os.path.abspath(__file__))
FONTS   = os.path.join(HERE, "assets", "fonts")
LOGODIR = os.path.join(HERE, "assets", "cfb-logos")
OUTDIR  = os.path.join(HERE, "output")

TEAM_ID = 130                      # ESPN id for Michigan
SEASON  = int(os.environ.get("MICH_SEASON", dt.date.today().year))
ET      = ZoneInfo("America/New_York")
DEBUG   = bool(os.environ.get("DEBUG_ESPN"))

W, H  = 1290, 2796
BLUE  = (0, 39, 76)         # Michigan blue
MAIZE = (255, 203, 5)       # Michigan maize
WHITE = (255, 255, 255)
DIM   = (150, 165, 185)

font = lambda n, s: ImageFont.truetype(os.path.join(FONTS, n), s)

API      = "https://api.collegefootballdata.com"
CFBD_KEY = os.environ.get("CFBD_API_KEY", "").strip()
TEAM     = "Michigan"

# ESPN team ids, used only to build logo URLs off their static CDN.
ESPN_ID = {
    "Western Michigan": "2711", "Oklahoma": "201", "UTEP": "2638", "Iowa": "2294",
    "Minnesota": "135", "Penn State": "213", "Indiana": "84", "Rutgers": "164",
    "Michigan State": "127", "Oregon": "2483", "UCLA": "26", "Ohio State": "194",
    "Michigan": "130",
}


def _g(d, *names, default=None):
    """CFBD has shipped both snake_case and camelCase. Accept either."""
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d[n]
    return default


def _cfbd(path, **params):
    if not CFBD_KEY:
        raise RuntimeError("CFBD_API_KEY is not set")
    r = requests.get(f"{API}{path}", params=params, timeout=30,
                     headers={"Authorization": f"Bearer {CFBD_KEY}",
                              "Accept": "application/json"})
    if r.status_code == 401:
        raise RuntimeError("CFBD rejected the API key (401) — check the secret")
    if r.status_code == 429:
        raise RuntimeError("CFBD monthly call limit reached (429)")
    r.raise_for_status()
    return r.json()


def _ap_ranks(season):
    """{school: rank} from the most recent AP Top 25.

    CFBD has filed the preseason poll under different seasonType/week values
    across seasons, so query broadly and keep the most recent AP poll found
    instead of assuming it lives under regular-season week 1.
    """
    def pull(**params):
        try:
            return _cfbd("/rankings", year=season, **params) or []
        except Exception as e:
            print(f"  ! rankings {params or '(all)'} unavailable: {e}",
                  file=sys.stderr)
            return []

    def has_ap(entries):
        return any("AP" in str(_g(p, "poll", default=""))
                   for wk in entries
                   for p in (_g(wk, "polls", default=[]) or []))

    entries = pull()                       # everything CFBD has for the year
    if not has_ap(entries):                # preseason-window fallbacks
        entries += pull(seasonType="preseason")
    if not has_ap(entries):
        entries += pull(seasonType="regular")

    def recency(wk):
        st = str(_g(wk, "seasonType", "season_type", default="regular")).lower()
        order = {"preseason": 0, "regular": 1, "postseason": 2}.get(st, 1)
        return (order, _g(wk, "week", default=0) or 0)

    best_key, out = None, {}
    for wk in entries:
        for poll in _g(wk, "polls", default=[]) or []:
            if "AP" not in str(_g(poll, "poll", default="")):
                continue
            k = recency(wk)
            if best_key is None or k >= best_key:
                best_key = k
                out = {_g(r, "school", "team"): _g(r, "rank")
                       for r in (_g(poll, "ranks", default=[]) or [])}
    if out:
        print(f"  AP poll: {len(out)} teams ranked (Michigan {out.get(TEAM, 'NR')})")
    else:
        print("  AP poll: none found across seasonTypes", file=sys.stderr)
    return out


def _media(season):
    """{(week, opponent): network} for TV listings."""
    out = {}
    try:
        data = _cfbd("/games/media", year=season, team=TEAM, seasonType="both")
    except Exception as e:
        print(f"  ! media unavailable: {e}", file=sys.stderr)
        return out
    for m in data or []:
        if str(_g(m, "mediaType", "media_type", default="")).lower() not in ("tv", "web", ""):
            continue
        gid = _g(m, "id", "gameId", "game_id")
        outlet = _g(m, "outlet")
        if gid and outlet and gid not in out:
            out[gid] = str(outlet).upper()
    return out


def fetch_schedule(season):
    games_raw = _cfbd("/games", year=season, team=TEAM, seasonType="both")
    print(f"  /games returned {len(games_raw or [])} games")
    ranks = _ap_ranks(season)
    tv = _media(season)

    games = []
    for gm in games_raw or []:
        home_team = _g(gm, "homeTeam", "home_team", default="")
        away_team = _g(gm, "awayTeam", "away_team", default="")
        is_home = home_team == TEAM
        opp = away_team if is_home else home_team
        if opp is None:
            continue

        raw = _g(gm, "startDate", "start_date")
        if not raw:
            continue
        start = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(ET)
        tbd = bool(_g(gm, "startTimeTbd", "start_time_tbd", default=False))

        us_pts   = _g(gm, "homePoints", "home_points") if is_home else _g(gm, "awayPoints", "away_points")
        them_pts = _g(gm, "awayPoints", "away_points") if is_home else _g(gm, "homePoints", "home_points")
        completed = bool(_g(gm, "completed", default=False))
        res = None
        if completed and us_pts is not None and them_pts is not None:
            res = "W" if us_pts > them_pts else ("L" if us_pts < them_pts else "T")

        eid = ESPN_ID.get(opp, "")
        games.append({
            "date": start.date(), "dt": start,
            "time": "TBD" if tbd else start.strftime("%-I:%M"),
            "ampm": "" if tbd else start.strftime("%p"),
            "opp": (opp or "?")[:4].upper(), "opp_name": opp, "opp_id": eid or opp,
            "opp_logo": (f"https://a.espncdn.com/i/teamlogos/ncaa/500/{eid}.png"
                         if eid else None),
            "opp_rank": ranks.get(opp), "my_rank": ranks.get(TEAM),
            "home": is_home,
            "neutral": bool(_g(gm, "neutralSite", "neutral_site", default=False)),
            "tv": tv.get(_g(gm, "id")),
            "conf_game": bool(_g(gm, "conferenceGame", "conference_game", default=False)),
            "final": completed, "res": res, "us": us_pts, "them": them_pts,
        })

    games.sort(key=lambda g: g["dt"])
    w = sum(1 for g in games if g["res"] == "W")
    l = sum(1 for g in games if g["res"] == "L")
    me = {"abbrev": "MICH",
          "logo": "https://a.espncdn.com/i/teamlogos/ncaa/500/130.png",
          "record": f"{w}-{l}", "conf": ""}
    return me, games


# --------------------------------------------------------- offline fallback
# The 2026 slate is fixed and public. If ESPN blocks us, render from this so
# there's still a correct wallpaper — just without live scores, ranks or TV.
# (id, month, day, opponent name, espn id, home?, kickoff ET or None, conf game?)
STATIC_2026 = [
    (1,  9,  5, "Western Michigan", "2711", True,  "7:30 PM", False),
    (2,  9, 12, "Oklahoma",         "201",  True,  "12:00 PM", False),
    (3,  9, 19, "UTEP",             "2638", True,  "3:30 PM", False),
    (4,  9, 26, "Iowa",             "2294", True,  None,      True),
    (5, 10,  3, "Minnesota",        "135",  False, None,      True),
    (6, 10, 17, "Penn State",       "213",  True,  None,      True),
    (7, 10, 24, "Indiana",          "84",   True,  None,      True),
    (8, 10, 31, "Rutgers",          "164",  False, None,      True),
    (9, 11,  7, "Michigan State",   "127",  True,  None,      True),
    (10, 11, 14, "Oregon",          "2483", False, None,      True),
    (11, 11, 21, "UCLA",            "26",   True,  None,      True),
    (12, 11, 28, "Ohio State",      "194",  False, "12:00 PM", True),
]


def static_schedule(season):
    me = {"abbrev": "MICH", "logo": None, "record": "0-0", "conf": ""}
    games = []
    for _, mo, dy, name, eid, home, kick, confg in STATIC_2026:
        date = dt.date(season, mo, dy)
        if kick:
            t, ap = kick.split(" ")
        else:
            t, ap = "TBD", ""
        games.append({
            "date": date, "dt": dt.datetime.combine(date, dt.time(12)).replace(tzinfo=ET),
            "time": t, "ampm": ap,
            "opp": name[:4].upper(), "opp_name": name, "opp_id": eid,
            "opp_logo": f"https://a.espncdn.com/i/teamlogos/ncaa/500/{eid}.png",
            "opp_rank": None, "my_rank": None,
            "home": home, "neutral": False, "tv": None,
            "conf_game": confg, "final": False, "res": None,
            "us": None, "them": None,
        })
    return me, games


# --------------------------------------------------------------------- logos
def get_logo(stem, url):
    """Use a bundled logo if one exists; otherwise pull from ESPN's CDN and cache it.

    Dropping a transparent PNG named <ABBREV>.png (or <espn-id>.png) into
    assets/cfb-logos/ overrides ESPN's version permanently — that's how the
    official Michigan block M gets used instead of ESPN's.
    """
    os.makedirs(LOGODIR, exist_ok=True)
    path = os.path.join(LOGODIR, f"{stem}.png")
    if not os.path.exists(path) and url:
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
        except Exception as e:
            print(f"  ! logo fetch failed for {stem}: {e}", file=sys.stderr)
            return None
    if not os.path.exists(path):
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def sample_bg(img, x, y, w, h):
    """Average colour of the backdrop where a logo is about to be drawn."""
    box = img.convert("RGB").crop((max(0, x), max(0, y), x + max(1, w), y + max(1, h)))
    box = box.resize((8, 8))
    px = box.load()
    tot = [0, 0, 0]
    for j in range(8):
        for i in range(8):
            p = px[i, j]
            tot[0] += p[0]; tot[1] += p[1]; tot[2] += p[2]
    return (tot[0] / 64, tot[1] / 64, tot[2] / 64)


def mean_visible_rgb(im):
    """Average colour of the logo's non-transparent pixels."""
    small = im.resize((32, 32))
    px = small.load()
    tot = [0, 0, 0]; n = 0
    for y in range(32):
        for x in range(32):
            r, g, b, al = px[x, y]
            if al > 60:
                tot[0] += r; tot[1] += g; tot[2] += b; n += 1
    if not n:
        return (255, 255, 255)
    return (tot[0] / n, tot[1] / n, tot[2] / n)


def needs_halo(im, bg):
    """True when the logo sits too close in colour to what's behind it.

    Brightness alone is the wrong test: Rutgers red is dark but reads fine
    against navy, while Penn State's navy lion vanishes into it.
    """
    r, g, b = mean_visible_rgb(im)
    dist = math.sqrt((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2)
    return dist < 78


def fit(im, bw, bh):
    s = min(bw / im.width, bh / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


def fade(im, a):
    if a >= 255:
        return im
    o = im.copy()
    o.putalpha(o.getchannel("A").point(lambda v: int(v * a / 255)))
    return o


# -------------------------------------------------------------------- render
SHORT = {
    "Western Michigan": "W. MICHIGAN", "Michigan State": "MICHIGAN ST",
    "Penn State": "PENN STATE", "Ohio State": "OHIO STATE",
}

# Layout is built around two things: iOS zooms wallpapers (~1.18x), and the
# home screen has apps on it. Everything lives in a compact central band with
# fat margins, so a zoom crop eats empty space instead of content.
# iOS zooms Shortcut-set wallpapers (measured 1.18x-1.5x on Ty's phone) and the
# crop anchor is not stable. So all content lives in a central box with a wide
# blue margin around it — the zoom eats padding instead of games.
SAFE_X0, SAFE_X1 = 130, 1160
BAND_TOP, BAND_BOT = 780, 1670


BG_IMAGE = os.path.join(HERE, "assets", "bg-michigan.png")


def backdrop(mich_logo):
    """Stadium photo if bundled, otherwise solid Michigan blue."""
    if os.path.exists(BG_IMAGE):
        ph = Image.open(BG_IMAGE).convert("RGB")
        # Scale past "fill" and anchor to the top, so the sunset stays up high
        # and the stadium drops below the schedule instead of hiding behind it.
        s = max(W / ph.width, H / ph.height) * 1.20
        ph = ph.resize((int(ph.width * s) + 1, int(ph.height * s) + 1), Image.LANCZOS)
        ox = (ph.width - W) // 2
        ph = ph.crop((ox, 0, ox + W, H))
        img = ph.convert("RGBA")

        # Cool the photo toward Michigan blue and knock it back so text wins.
        tint = Image.new("RGBA", (W, H), BLUE + (105,))
        img = Image.alpha_composite(img, tint)
        img = Image.alpha_composite(img, Image.new("RGBA", (W, H), (0, 0, 0, 70)))

        # Extra scrim behind the schedule band, faded at both edges.
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scrim)
        top, bot = BAND_TOP - 110, BAND_BOT + 90
        for y in range(top, bot):
            t = (y - top) / max(1, bot - top)
            edge = min(1.0, min(t, 1 - t) * 7)         # soft top/bottom falloff
            sd.line([(0, y), (W, y)], fill=(2, 10, 24, int(150 * edge)))
        img = Image.alpha_composite(img, scrim.filter(ImageFilter.GaussianBlur(6)))
        return img

    bg = Image.new("RGB", (W, H), BLUE)
    px = bg.load()
    cx, cy = W * 0.5, H * 0.44
    for y in range(H):
        for x in range(0, W, 2):
            d = math.hypot((x - cx) / (W * 0.95), (y - cy) / (H * 0.72))
            k = max(0.0, min(1.0, (d - 0.45) * 0.95))
            c = (int(BLUE[0] * (1 - k) + 2 * k), int(BLUE[1] * (1 - k) + 10 * k),
                 int(BLUE[2] * (1 - k) + 24 * k))
            px[x, y] = c
            if x + 1 < W:
                px[x + 1, y] = c
    img = bg.filter(ImageFilter.GaussianBlur(4)).convert("RGBA")
    if mich_logo:
        gh = fade(fit(mich_logo, 620, 620), 30)
        img.alpha_composite(gh, ((W - gh.width) // 2, 1830))
    return img


MON = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
       "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def build(me, games, logos):
    img = backdrop(logos.get("MICH"))
    d = ImageDraw.Draw(img)
    today = dt.date.today()

    # ---------------------------------------------------------- header
    mf = font("BigShoulders-Bold.ttf", 98)
    bb = d.textbbox((0, 0), "MICHIGAN", font=mf)
    d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], BAND_TOP), "MICHIGAN", font=mf,
           fill=MAIZE + (255,))
    my_rank = next((g["my_rank"] for g in games if g["my_rank"]), None)
    cw_ = sum(1 for g in games if g["conf_game"] and g["res"] == "W")
    cl_ = sum(1 for g in games if g["conf_game"] and g["res"] == "L")
    bits = f"{me['record']}  OVERALL     {cw_}-{cl_}  BIG TEN     " + \
           (f"#{my_rank}  AP" if my_rank else "NR")
    rf = font("GeistMono-Bold.ttf", 26)
    bb = d.textbbox((0, 0), bits, font=rf)
    d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], BAND_TOP + 104), bits,
           font=rf, fill=(255, 255, 255, 235))

    # ---------------------------------------------------------- game grid
    GTOP = BAND_TOP + 152
    COLS, CGAP, RGAP = 2, 24, 12
    CW_ = (SAFE_X1 - SAFE_X0 - CGAP) // COLS
    n = len(games)
    per = (n + COLS - 1) // COLS
    CH_ = min(124, (BAND_BOT - GTOP - (per - 1) * RGAP) // max(1, per))

    date_f = font("GeistMono-Bold.ttf", 24)
    name_f = font("BigShoulders-Bold.ttf", 53)
    rank_f = font("GeistMono-Bold.ttf", 24)
    va_f   = font("GeistMono-Bold.ttf", 17)
    time_f = font("BigShoulders-Bold.ttf", 45)
    tv_f   = font("GeistMono-Regular.ttf", 19)
    res_f  = font("GeistMono-Bold.ttf", 35)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    for i, g in enumerate(games):
        col, row = divmod(i, per)          # column-major: each column reads down
        x = SAFE_X0 + col * (CW_ + CGAP)
        y = GTOP + row * (CH_ + RGAP)
        a = 135 if g["final"] else 255

        ld.rounded_rectangle([x, y + 4, x + 7, y + CH_ - 4], radius=4,
                             fill=(MAIZE if g["home"] else (165, 180, 200)) + (a,))

        ds = f"{MON[g['date'].month]} {g['date'].day}"
        ld.text((x + 23, y + 12), ds, font=date_f, fill=(255, 255, 255, int(a * 0.75)))

        # right side: result or kickoff
        rx = x + CW_ - 17
        if g["final"] and g["res"]:
            txt = f"{g['res']} {g['us']}-{g['them']}"
            bb = ld.textbbox((0, 0), txt, font=res_f)
            ld.text((rx - (bb[2] - bb[0]) - bb[0], y + 10), txt, font=res_f,
                    fill=(MAIZE if g["res"] == "W" else (235, 150, 150)) + (255,))
        else:
            t = g["time"] if g["time"] == "TBD" else f"{g['time']} {g['ampm']}"
            bb = ld.textbbox((0, 0), t, font=time_f)
            ld.text((rx - (bb[2] - bb[0]) - bb[0], y + 6), t, font=time_f,
                    fill=(255, 255, 255, 240))
            if g["tv"]:
                bb = ld.textbbox((0, 0), g["tv"], font=tv_f)
                ld.text((rx - (bb[2] - bb[0]) - bb[0], y + 50), g["tv"],
                        font=tv_f, fill=MAIZE + (215,))

        # logo + opponent
        lg = logos.get(g["opp_id"])
        ly = y + CH_ - 72
        if lg:
            box = 58
            l2 = fade(fit(lg, box, box), a)
            lx = x + 20 + (box - l2.width) // 2
            lyy = ly + (58 - l2.height) // 2
            # Dark marks (Penn State's navy lion, Iowa's black hawkeye) disappear
            # against the navy photo. Lay a soft light halo behind them.
            if needs_halo(l2, sample_bg(img, lx, lyy, l2.width, l2.height)):
                pad = 10
                halo = Image.new("RGBA", (l2.width + pad * 2, l2.height + pad * 2),
                                 (255, 255, 255, 0))
                shape = Image.new("RGBA", l2.size, (245, 248, 255, 0))
                shape.putalpha(l2.getchannel("A").point(lambda v: int(v * 0.95)))
                halo.alpha_composite(shape, (pad, pad))
                halo = halo.filter(ImageFilter.GaussianBlur(7))
                halo = fade(halo, min(255, int(a * 1.0)))
                layer.alpha_composite(halo, (lx - pad, lyy - pad))
                layer.alpha_composite(halo, (lx - pad, lyy - pad))   # twice = denser
            layer.alpha_composite(l2, (lx, lyy))
        tx = x + (88 if lg else 26)
        if g["opp_rank"]:
            rk = f"#{g['opp_rank']}"
            ld.text((tx, ly + 12), rk, font=rank_f, fill=MAIZE + (a,))
            tx += ld.textbbox((0, 0), rk, font=rank_f)[2] + 9
        nm = SHORT.get(g["opp_name"], g["opp_name"]).upper()
        ld.text((tx, ly - 2), nm, font=name_f, fill=(255, 255, 255, a))

        if g["date"] == today:
            ld.rounded_rectangle([x - 4, y - 4, x + CW_ + 4, y + CH_ + 4],
                                 radius=12, outline=MAIZE + (245,), width=3)

    img = Image.alpha_composite(img, layer)

    # ---------------------------------------------------------- footer
    d2 = ImageDraw.Draw(img)
    ff = font("GeistMono-Regular.ttf", 21)
    foot = "MAIZE = HOME     ALL TIMES ET     BYE OCT 10"
    bb = d2.textbbox((0, 0), foot, font=ff)
    d2.text(((W - (bb[2] - bb[0])) // 2 - bb[0], BAND_BOT + 12), foot,
            font=ff, fill=(255, 255, 255, 120))
    return img.convert("RGB")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    live = True
    try:
        me, games = fetch_schedule(SEASON)
        if not games:
            raise RuntimeError("ESPN returned zero games")
    except Exception as e:
        print(f"!! CFBD unavailable ({e})", file=sys.stderr)
        print("!! Falling back to the bundled 2026 schedule "
              "(no live scores, ranks or TV).", file=sys.stderr)
        me, games = static_schedule(SEASON)
        live = False
    print("DATA SOURCE:", "CFBD (live)" if live else "bundled static schedule")

    logos = {"MICH": get_logo("MICH", me["logo"])}
    for g in games:
        if g["opp_id"] and g["opp_id"] not in logos:
            logos[g["opp_id"]] = get_logo(g["opp_id"], g["opp_logo"])

    print(f"Michigan {SEASON}: {len(games)} games | record {me['record']} | {me['conf']}")
    for g in games:
        rk = f"#{g['opp_rank']} " if g["opp_rank"] else ""
        wh = "vs" if g["home"] else "at"
        rr = f"{g['res']} {g['us']}-{g['them']}" if g["final"] else f"{g['time']} {g['ampm']} {g['tv'] or 'TV TBD'}"
        print(f"  {g['date']}  {wh} {rk}{g['opp_name']:<22} {rr}")
    if DEBUG:
        print("\n--- parsed payload ---")
        print(json.dumps([{k: str(v) for k, v in g.items()} for g in games], indent=1)[:4000])

    img = build(me, games, logos)
    out = os.path.join(OUTDIR, "michigan.png")
    img.save(out)
    print("->", out)


if __name__ == "__main__":
    main()
