#!/usr/bin/env python3
"""
Michigan Football schedule wallpaper (1290x2796), rendered from ESPN's public API.

Shows every game on one page with: date, opponent logo + AP rank, home/away,
kickoff time (ET) or final score with W/L, and the TV network. Header carries
Michigan's own rank and overall / Big Ten records.

No API key needed. Logos are pulled from ESPN's CDN and cached in assets/cfb-logos/.

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

API = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
UA  = {"User-Agent": "Mozilla/5.0 (michigan-wallpaper)"}

font = lambda n, s: ImageFont.truetype(os.path.join(FONTS, n), s)


# ------------------------------------------------------------------ ESPN feed
def _first(d, *path, default=None):
    """Safely walk nested dicts/lists."""
    cur = d
    for p in path:
        try:
            cur = cur[p]
        except (KeyError, IndexError, TypeError):
            return default
    return cur if cur is not None else default


def _score(c):
    s = c.get("score")
    if isinstance(s, dict):
        s = s.get("value", s.get("displayValue"))
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _rank(c):
    r = _first(c, "curatedRank", "current")
    try:
        r = int(r)
    except (TypeError, ValueError):
        return None
    return r if 1 <= r <= 25 else None      # ESPN uses 99 for unranked


def _network(comp):
    for b in comp.get("broadcasts") or []:
        n = _first(b, "media", "shortName") or _first(b, "names", 0) or b.get("shortName")
        if n:
            return str(n).upper()
    for b in comp.get("geoBroadcasts") or []:
        n = _first(b, "media", "shortName")
        if n:
            return str(n).upper()
    return None


def fetch_schedule(season):
    r = requests.get(f"{API}/teams/{TEAM_ID}/schedule",
                     params={"season": season}, headers=UA, timeout=30)
    r.raise_for_status()
    data = r.json()

    team = data.get("team") or {}
    me = {
        "abbrev": team.get("abbreviation", "MICH"),
        "logo":   _first(team, "logos", 0, "href"),
        "record": team.get("recordSummary") or "0-0",
        "conf":   team.get("standingSummary") or "",
    }

    games = []
    for ev in data.get("events") or []:
        comp = _first(ev, "competitions", 0, default={})
        comps = comp.get("competitors") or []
        us = next((c for c in comps if str(_first(c, "team", "id")) == str(TEAM_ID)), None)
        them = next((c for c in comps if c is not us), None)
        if not us or not them:
            continue

        start = dt.datetime.fromisoformat(
            (comp.get("date") or ev.get("date")).replace("Z", "+00:00")).astimezone(ET)
        state = _first(comp, "status", "type", "name", default="STATUS_SCHEDULED")
        final = state == "STATUS_FINAL" or bool(_first(comp, "status", "type", "completed"))

        us_s, them_s = _score(us), _score(them)
        res = None
        if final and us_s is not None and them_s is not None:
            res = "W" if us_s > them_s else ("L" if us_s < them_s else "T")

        # ESPN writes "9/5 - TBD" in shortDetail when kickoff isn't announced yet
        detail = str(_first(comp, "status", "type", "shortDetail", default="")).upper()
        time_known = "TBD" not in detail

        opp_team = them.get("team") or {}
        games.append({
            "date":    start.date(),
            "dt":      start,
            "time":    start.strftime("%-I:%M").lstrip("0") if time_known else "TBD",
            "ampm":    start.strftime("%p") if time_known else "",
            "opp":     opp_team.get("abbreviation") or opp_team.get("shortDisplayName") or "?",
            "opp_name": (opp_team.get("shortDisplayName") or opp_team.get("location")
                         or opp_team.get("displayName") or "?"),
            "opp_id":  str(opp_team.get("id") or ""),
            "opp_logo": _first(opp_team, "logos", 0, "href"),
            "opp_rank": _rank(them),
            "my_rank": _rank(us),
            "home":    us.get("homeAway") == "home",
            "neutral": bool(comp.get("neutralSite")),
            "tv":      _network(comp),
            "final":   final,
            "res":     res,
            "us":      us_s,
            "them":    them_s,
        })

    games.sort(key=lambda g: g["dt"])
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


def is_dark(im):
    """True if the logo's visible pixels are mostly dark (needs a glow on navy)."""
    small = im.resize((32, 32))
    px = small.load()
    tot = n = 0
    for y in range(32):
        for x in range(32):
            r, g, b, a = px[x, y]
            if a > 60:
                tot += 0.299 * r + 0.587 * g + 0.114 * b
                n += 1
    return n > 0 and (tot / n) < 78


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
def backdrop(mich_logo):
    bg = Image.new("RGB", (W, H), (3, 8, 16))
    px = bg.load()
    cx, cy = W * 0.5, H * 0.30
    for y in range(H):
        for x in range(0, W, 2):
            g = max(0.0, 1.0 - math.hypot((x - cx) / (W * 1.15), (y - cy) / (H * 0.62))) ** 1.6
            m = max(0.0, 1.0 - math.hypot((x - cx) / (W * 0.75), (y - H * 0.99) / (H * 0.20))) ** 2.8
            c = (min(255, int(3 + BLUE[0] * g * 2.7 + MAIZE[0] * m * 0.10)),
                 min(255, int(8 + BLUE[1] * g * 2.7 + MAIZE[1] * m * 0.10)),
                 min(255, int(16 + BLUE[2] * g * 2.7 + MAIZE[2] * m * 0.10)))
            px[x, y] = c
            if x + 1 < W:
                px[x + 1, y] = c
    img = bg.filter(ImageFilter.GaussianBlur(3)).convert("RGBA")
    if mich_logo:
        gh = fade(fit(mich_logo, 340, 340), 26)
        for gx, gy in [(-110, 40), (1060, 250), (-90, 2320)]:
            img.alpha_composite(gh, (gx, gy))
    return img


MON = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
       "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def build(me, games, logos):
    img = backdrop(logos.get("MICH"))
    d = ImageDraw.Draw(img)

    # ---- header ---------------------------------------------------------
    mf = font("BigShoulders-Bold.ttf", 178)
    bb = d.textbbox((0, 0), "MICHIGAN", font=mf)
    d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], 560), "MICHIGAN", font=mf,
           fill=(0, 0, 0, 0), stroke_width=5, stroke_fill=MAIZE + (215,))
    sf = font("GeistMono-Bold.ttf", 34)
    sub = f"F O O T B A L L   {SEASON}"
    bb = d.textbbox((0, 0), sub, font=sf)
    d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], 742), sub, font=sf, fill=(255, 255, 255, 190))

    # ---- stat strip: overall / big ten / rank ---------------------------
    my_rank = next((g["my_rank"] for g in games if g["my_rank"]), None)
    conf = me["conf"] or ""
    if "Big Ten" in conf:
        conf_rec = conf.replace("Big Ten", "").strip().split()[0] if conf.split() else "0-0"
    else:
        conf_rec = conf.strip() or "--"
    stats = [(me["record"], "OVERALL"), (conf_rec, "BIG TEN"),
             (f"#{my_rank}" if my_rank else "NR", "AP RANK")]
    nf, lf = font("BigShoulders-Bold.ttf", 82), font("GeistMono-Regular.ttf", 22)
    colw = 340
    x0 = (W - colw * len(stats)) // 2
    for i, (val, lab) in enumerate(stats):
        cx = x0 + i * colw + colw // 2
        bb = d.textbbox((0, 0), val, font=nf)
        d.text((cx - (bb[2] - bb[0]) // 2 - bb[0], 812), val, font=nf, fill=WHITE + (255,))
        bb = d.textbbox((0, 0), lab, font=lf)
        d.text((cx - (bb[2] - bb[0]) // 2 - bb[0], 902), lab, font=lf, fill=DIM + (215,))
        if i:
            d.line([(x0 + i * colw, 822), (x0 + i * colw, 916)], fill=(255, 255, 255, 45), width=2)

    # ---- game rows ------------------------------------------------------
    M, TOP = 78, 990
    RW = W - 2 * M
    rows = len(games) + 1                       # +1 for the bye week
    RH = min(112, (2440 - TOP - (rows - 1) * 9) // max(1, rows))
    GAP = 9

    date_f  = font("GeistMono-Bold.ttf", 25)
    name_f  = font("BigShoulders-Bold.ttf", 54)
    rank_f  = font("GeistMono-Bold.ttf", 26)
    va_f    = font("GeistMono-Bold.ttf", 23)
    time_f  = font("BigShoulders-Bold.ttf", 44)
    tv_f    = font("GeistMono-Regular.ttf", 21)
    res_f   = font("BigShoulders-Bold.ttf", 50)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    today = dt.date.today()

    # find the bye: the gap between consecutive games longer than 8 days
    bye_after = None
    for a, b in zip(games, games[1:]):
        if (b["date"] - a["date"]).days > 10:
            bye_after = a["date"]
            break

    y = TOP
    drawn = 0
    for g in games:
        a = 130 if g["final"] else 255
        ld.rounded_rectangle([M, y, M + RW, y + RH], radius=8,
                             fill=(255, 255, 255, 12),
                             outline=(255, 255, 255, int(a * 0.30)), width=2)
        # home/away edge stripe
        ld.rounded_rectangle([M, y, M + 9, y + RH], radius=4,
                             fill=(MAIZE if g["home"] else (170, 185, 205)) + (a,))

        # date
        ds = f"{MON[g['date'].month]} {g['date'].day}"
        ld.text((M + 26, y + RH // 2 - 15), ds, font=date_f, fill=(WHITE if not g["final"] else DIM) + (a,))

        # opponent logo
        lg = logos.get(g["opp_id"])
        lx = M + 152
        if lg:
            box = int(RH * 0.66)
            l2 = fade(fit(lg, box, box), a)
            if is_dark(l2):
                glow = Image.new("RGBA", l2.size, (255, 255, 255, 0))
                glow.putalpha(l2.getchannel("A").point(lambda v: int(v * 0.55)))
                gb = glow.filter(ImageFilter.GaussianBlur(9))
                layer.alpha_composite(gb, (lx, y + (RH - l2.height) // 2))
            layer.alpha_composite(l2, (lx + (box - l2.width) // 2, y + (RH - l2.height) // 2))

        # vs/at + rank + name
        tx = M + 246
        va = "AT" if (not g["home"] and not g["neutral"]) else ("VS" if g["home"] else "N")
        ld.text((tx, y + RH // 2 - 26), va, font=va_f, fill=(DIM) + (a,))
        tx += 46
        if g["opp_rank"]:
            rk = f"#{g['opp_rank']}"
            ld.text((tx, y + RH // 2 - 25), rk, font=rank_f, fill=MAIZE + (a,))
            bb = ld.textbbox((0, 0), rk, font=rank_f)
            tx += (bb[2] - bb[0]) + 12
        nm = g["opp_name"].upper()
        ld.text((tx, y + RH // 2 - 36), nm, font=name_f, fill=WHITE + (a,))

        # right block: result or time+tv
        rx = M + RW - 24
        if g["final"] and g["res"]:
            sc = f"{g['us']}-{g['them']}"
            bb = ld.textbbox((0, 0), sc, font=res_f)
            ld.text((rx - (bb[2] - bb[0]) - bb[0], y + RH // 2 - 32), sc, font=res_f,
                    fill=WHITE + (a,))
            badge = g["res"]
            bw2 = 42
            bx = rx - (bb[2] - bb[0]) - bw2 - 20
            col = MAIZE if badge == "W" else (150, 60, 60)
            ld.rounded_rectangle([bx, y + RH // 2 - 26, bx + bw2, y + RH // 2 + 22],
                                 radius=6, fill=col + (235,))
            bf = font("BigShoulders-Bold.ttf", 40)
            bb2 = ld.textbbox((0, 0), badge, font=bf)
            ld.text((bx + (bw2 - (bb2[2] - bb2[0])) // 2 - bb2[0], y + RH // 2 - 30),
                    badge, font=bf, fill=(BLUE if badge == "W" else WHITE) + (255,))
        else:
            t = g["time"] if g["time"] == "TBD" else f"{g['time']} {g['ampm']}"
            bb = ld.textbbox((0, 0), t, font=time_f)
            ld.text((rx - (bb[2] - bb[0]) - bb[0], y + RH // 2 - 34), t, font=time_f,
                    fill=WHITE + (230,))
            tv = g["tv"] or ""
            if tv:
                bb = ld.textbbox((0, 0), tv, font=tv_f)
                ld.text((rx - (bb[2] - bb[0]) - bb[0], y + RH // 2 + 10), tv,
                        font=tv_f, fill=MAIZE + (200,))

        if g["date"] == today:
            ld.rounded_rectangle([M - 5, y - 5, M + RW + 5, y + RH + 5], radius=10,
                                 outline=MAIZE + (240,), width=3)
        y += RH + GAP
        drawn += 1

        if bye_after and g["date"] == bye_after:
            bh = int(RH * 0.44)
            ld.line([(M + 30, y + bh // 2), (M + RW - 30, y + bh // 2)],
                    fill=(255, 255, 255, 30), width=2)
            bf2 = font("GeistMono-Regular.ttf", 21)
            lab = "  B Y E   W E E K  "
            bb = ld.textbbox((0, 0), lab, font=bf2)
            lw = bb[2] - bb[0]
            ld.rectangle([(W - lw) // 2 - 10, y + bh // 2 - 15, (W + lw) // 2 + 10, y + bh // 2 + 17],
                         fill=(6, 14, 28, 255))
            ld.text(((W - lw) // 2 - bb[0], y + bh // 2 - 12), lab, font=bf2, fill=DIM + (190,))
            y += bh + GAP

    img = Image.alpha_composite(img, layer)

    # ---- footer ---------------------------------------------------------
    d2 = ImageDraw.Draw(img)
    ff = font("GeistMono-Regular.ttf", 22)
    foot = "A L L   T I M E S   E T"
    bb = d2.textbbox((0, 0), foot, font=ff)
    d2.text(((W - (bb[2] - bb[0])) // 2 - bb[0], min(y + 16, 2500)), foot,
            font=ff, fill=(255, 255, 255, 100))

    ml = logos.get("MICH")
    if ml:
        hero = fit(ml, 190, 190)
        hy = min(y + 60, 2545)
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gg = Image.new("RGBA", hero.size, (255, 210, 60, 0))
        gg.putalpha(hero.getchannel("A").point(lambda v: int(v * 0.5)))
        glow.alpha_composite(gg, ((W - hero.width) // 2, hy))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(30)))
        img.alpha_composite(hero, ((W - hero.width) // 2, hy))

    return img.convert("RGB")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    try:
        me, games = fetch_schedule(SEASON)
    except Exception as e:
        print("ERROR fetching ESPN schedule:", e, file=sys.stderr)
        sys.exit(1)
    if not games:
        print("No games returned — check the season year.", file=sys.stderr)
        sys.exit(1)

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
