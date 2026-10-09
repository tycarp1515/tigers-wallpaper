#!/usr/bin/env python3
"""
Weekly lookahead lock-screen wallpaper (1290x2796).

Top: one card per football team (Lions, Vikings, Michigan, Minnesota, WMU) with
record, AP rank for college teams, last result, and the next game (or BYE).
Bottom: a Mon-Sun strip for the nightly teams (Red Wings, Pistons, college
hockey and hoops). A strip row only appears in a week that team plays, so the
screen stays tidy in the off-season and fills in as seasons start.

Content sits between the lock-screen clock and the flashlight/camera buttons.

Data sources (all free):
    NFL           nflverse games.csv on GitHub (no key)
    College FB    CollegeFootballData (CFBD_API_KEY secret) - 3 calls per run
    NHL           api-web.nhle.com (no key)
    NBA           cdn.nba.com schedule JSON (no key)
    College hockey/hoops   ESPN site API (no key; rows are skipped if ESPN blocks)
Every team is fetched on its own, so one bad feed never kills the image.

    python render_lookahead.py           # live data
    python render_lookahead.py --mock    # sample data, no network (layout check)

Env:
    CFBD_API_KEY      CollegeFootballData key (college football cards)
    LOOKAHEAD_DATE    pretend today is YYYY-MM-DD (testing)
"""

import os, sys, io, csv, json, math, random, datetime as dt
from zoneinfo import ZoneInfo
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE     = os.path.dirname(os.path.abspath(__file__))
FONTS    = os.path.join(HERE, "assets", "fonts")
LOGODIR  = os.path.join(HERE, "assets", "logos")
OUTDIR   = os.path.join(HERE, "output")
BG_IMAGE = os.path.join(HERE, "assets", "bg-lookahead.png")
ET       = ZoneInfo("America/New_York")

W, H = 1290, 2796
BAND_TOP, BAND_BOT = 655, 2425      # under the clock / above the lock-screen buttons
X0, X1 = 58, 1232

WHITE = (255, 255, 255)
DIM   = (160, 172, 190)
GOLD  = (242, 193, 78)
WINC  = (120, 222, 150)
LOSSC = (240, 125, 112)

CFBD_KEY = os.environ.get("CFBD_API_KEY", "").strip()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
      "Accept": "application/json,text/csv,*/*"}

# ------------------------------------------------------------------ teams
# Order here is the order on screen. kind: "card" = football card, "strip" = Mon-Sun row.
TEAMS = [
    dict(key="DET-NFL",  kind="card",  league="nfl",   name="LIONS",       code="DET",              color=(0, 118, 182)),
    dict(key="MIN-NFL",  kind="card",  league="nfl",   name="VIKINGS",     code="MIN",              color=(110, 60, 175)),
    dict(key="MICH-CFB", kind="card",  league="cfb",   name="MICHIGAN",    code="Michigan",         espn="130",  color=(255, 203, 5)),
    dict(key="MINN-CFB", kind="card",  league="cfb",   name="MINNESOTA",   code="Minnesota",        espn="135",  color=(160, 20, 45)),
    dict(key="WMU-CFB",  kind="card",  league="cfb",   name="W. MICHIGAN", code="Western Michigan", espn="2711", color=(181, 161, 103)),
    dict(key="DET-NHL",  kind="strip", league="nhl",   name="RED WINGS",   code="DET",              color=(206, 17, 38)),
    dict(key="DET-NBA",  kind="strip", league="nba",   name="PISTONS",     code="DET",              color=(29, 66, 186)),
    dict(key="MICH-HKY", kind="strip", league="ncaah", name="MICHIGAN",    sub="HOCKEY", espn="130",  color=(255, 203, 5)),
    dict(key="MINN-HKY", kind="strip", league="ncaah", name="MINNESOTA",   sub="HOCKEY", espn="135",  color=(160, 20, 45)),
    dict(key="WMU-HKY",  kind="strip", league="ncaah", name="W. MICHIGAN", sub="HOCKEY", espn="2711", color=(181, 161, 103)),
    dict(key="MICH-BB",  kind="strip", league="ncaab", name="MICHIGAN",    sub="HOOPS",  espn="130",  color=(255, 203, 5)),
    dict(key="MINN-BB",  kind="strip", league="ncaab", name="MINNESOTA",   sub="HOOPS",  espn="135",  color=(160, 20, 45)),
    dict(key="WMU-BB",   kind="strip", league="ncaab", name="W. MICHIGAN", sub="HOOPS",  espn="2711", color=(181, 161, 103)),
]

# ESPN logo-CDN abbreviations that differ from each league's own codes.
NFL_ESPN = {"LA": "lar", "WAS": "wsh", "LV": "lv", "LAC": "lac"}
NHL_ESPN = {"TBL": "tb", "NJD": "nj", "LAK": "la", "SJS": "sj", "UTA": "utah", "WSH": "wsh"}
NBA_ESPN = {"GSW": "gs", "NYK": "ny", "SAS": "sa", "NOP": "no", "UTA": "utah", "WAS": "wsh"}
LOGO_OVERRIDE = {"ncaa-130": os.path.join(HERE, "assets", "cfb-logos", "MICH.png")}


def espn_logo(path):
    return f"https://a.espncdn.com/i/teamlogos/{path}.png"


def game(start, home, opp, opp_logo_key, opp_logo_url, us=None, them=None,
         final=False, tbd=False, tv=None, reg=True, opp_rank=None, conf=False, ot=False):
    return dict(dt=start, home=home, opp=opp, logo_key=opp_logo_key, logo_url=opp_logo_url,
                us=us, them=them, final=final, tbd=tbd, tv=tv, reg=reg,
                opp_rank=opp_rank, conf=conf, ot=ot)


def wl(games, ties=False):
    fin = [g for g in games if g["final"] and g["reg"] and g["us"] is not None]
    w = sum(g["us"] > g["them"] for g in fin)
    l = sum(g["us"] < g["them"] for g in fin)
    t = sum(g["us"] == g["them"] for g in fin)
    return f"{w}-{l}-{t}" if (ties and t) else f"{w}-{l}"


def get_json(url, **params):
    r = requests.get(url, params=params or None, headers=UA, timeout=45)
    r.raise_for_status()
    return r.json()


def football_season(today):
    return today.year if today.month >= 3 else today.year - 1


# ------------------------------------------------------------------- NFL
_nfl_rows = None


def fetch_nfl(t, today):
    global _nfl_rows
    if _nfl_rows is None:
        r = requests.get("https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
                         headers=UA, timeout=60)
        r.raise_for_status()
        _nfl_rows = list(csv.DictReader(io.StringIO(r.text)))
    season, code, games = str(football_season(today)), t["code"], []
    for g in _nfl_rows:
        if g.get("season") != season or code not in (g.get("home_team"), g.get("away_team")):
            continue
        home = g["home_team"] == code
        opp = g["away_team"] if home else g["home_team"]
        gt = (g.get("gametime") or "").strip()
        hh, mm = (int(x) for x in gt.split(":")[:2]) if gt else (13, 0)
        start = dt.datetime.strptime(g["gameday"], "%Y-%m-%d").replace(hour=hh, minute=mm, tzinfo=ET)
        hs, as_ = g.get("home_score", ""), g.get("away_score", "")
        final = hs not in ("", "NA") and as_ not in ("", "NA")
        us = them = None
        if final:
            us, them = (int(float(hs)), int(float(as_))) if home else (int(float(as_)), int(float(hs)))
        games.append(game(start, home, opp, f"nfl-{opp}", espn_logo(f"nfl/500/{NFL_ESPN.get(opp, opp.lower())}"),
                          us, them, final, tbd=not gt, tv=(g.get("network") or None),
                          reg=g.get("game_type") == "REG", ot=g.get("overtime") == "1"))
    return dict(record=wl(games, ties=True), rank=None,
                logo=("nfl-" + code, espn_logo(f"nfl/500/{code.lower()}")), games=games)


# ------------------------------------------------------------ College FB
_cfbd_cache = {}


def cfbd(path, **params):
    if not CFBD_KEY:
        raise RuntimeError("CFBD_API_KEY is not set")
    k = (path, tuple(sorted(params.items())))
    if k not in _cfbd_cache:
        r = requests.get("https://api.collegefootballdata.com" + path, params=params, timeout=60,
                         headers={"Authorization": f"Bearer {CFBD_KEY}", "Accept": "application/json"})
        if r.status_code == 401:
            raise RuntimeError("CFBD rejected the key (401)")
        if r.status_code == 429:
            raise RuntimeError("CFBD monthly limit reached (429)")
        r.raise_for_status()
        _cfbd_cache[k] = r.json() or []
    return _cfbd_cache[k]


def _g(d, *names, default=None):
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None:
            return d[n]
    return default


_ranks = None


def ap_ranks(season):
    """Most recent AP Top 25, whichever seasonType CFBD files it under."""
    global _ranks
    if _ranks is not None:
        return _ranks
    entries = []
    for st in (None, "preseason", "regular", "postseason"):
        try:
            entries += cfbd("/rankings", year=season, **({"seasonType": st} if st else {}))
        except Exception as e:
            print(f"  ! rankings {st or 'all'}: {e}", file=sys.stderr)
        if any("AP" in str(_g(p, "poll", default="")) for w in entries for p in _g(w, "polls", default=[]) or []):
            break
    order = {"preseason": 0, "regular": 1, "postseason": 2}
    best, out = None, {}
    for w in entries:
        key = (order.get(str(_g(w, "seasonType", "season_type", default="regular")).lower(), 1),
               _g(w, "week", default=0) or 0)
        for p in _g(w, "polls", default=[]) or []:
            if "AP" in str(_g(p, "poll", default="")) and (best is None or key >= best):
                best = key
                out = {_g(r, "school", "team"): _g(r, "rank") for r in _g(p, "ranks", default=[]) or []}
    _ranks = out
    print(f"  AP poll: {len(out)} ranked")
    return out


CFB_CACHE = os.path.join(HERE, "assets", "cache", "cfbd.json")
CFB_CACHE_HOURS = 3          # hourly runs x 3 calls would blow the free 1,000/month; this keeps it ~750
_cfb_bundle = None


def cfb_bundle(season):
    """Games/TV/AP poll for our college teams, cached on disk so the hourly runs only
    call CollegeFootballData every few hours. A stale cache is still used if CFBD fails."""
    global _cfb_bundle
    if _cfb_bundle is not None:
        return _cfb_bundle
    cached = None
    try:
        with open(CFB_CACHE) as fh:
            cached = json.load(fh)
    except Exception:
        pass
    now = dt.datetime.now(dt.timezone.utc)
    if cached and cached.get("season") == season:
        age = now - dt.datetime.fromisoformat(cached["fetched"])
        if age < dt.timedelta(hours=CFB_CACHE_HOURS):
            print(f"  CFBD cache: {int(age.total_seconds() // 60)} min old, reusing")
            _cfb_bundle = cached
            return cached
    try:
        names = {t["code"] for t in TEAMS if t["league"] == "cfb"}
        games = [g for g in cfbd("/games", year=season, seasonType="both")
                 if _g(g, "homeTeam", "home_team") in names or _g(g, "awayTeam", "away_team") in names]
        ids = {_g(g, "id") for g in games}
        try:
            media = [m for m in cfbd("/games/media", year=season, seasonType="both")
                     if _g(m, "id", "gameId", "game_id") in ids]
        except Exception as e:
            print(f"  ! media: {e}", file=sys.stderr)
            media = []
        bundle = dict(season=season, fetched=now.isoformat(), games=games, media=media, ranks=ap_ranks(season))
        os.makedirs(os.path.dirname(CFB_CACHE), exist_ok=True)
        with open(CFB_CACHE, "w") as fh:
            json.dump(bundle, fh)
        print(f"  CFBD: fetched {len(games)} games, cache saved")
    except Exception as e:
        if not cached:
            raise
        print(f"  ! CFBD fetch failed ({e}); using older cache", file=sys.stderr)
        bundle = cached
    _cfb_bundle = bundle
    return bundle


def fetch_cfb(t, today):
    season = football_season(today)
    b = cfb_bundle(season)
    allg, ranks, media = b["games"], b.get("ranks") or {}, b.get("media") or []
    tv = {}
    for m in media:
        gid, outlet = _g(m, "id", "gameId", "game_id"), _g(m, "outlet")
        if gid and outlet and gid not in tv:
            tv[gid] = str(outlet).upper()
    name, games = t["code"], []
    for g in allg:
        ht, at = _g(g, "homeTeam", "home_team"), _g(g, "awayTeam", "away_team")
        if name not in (ht, at):
            continue
        home = ht == name
        opp = at if home else ht
        oid = _g(g, "awayId", "away_id") if home else _g(g, "homeId", "home_id")
        raw = _g(g, "startDate", "start_date")
        if not raw:
            continue
        start = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(ET)
        tbd = bool(_g(g, "startTimeTbd", "start_time_tbd", default=False)) or (start.hour == 0 and start.minute == 0)
        hp, ap = _g(g, "homePoints", "home_points"), _g(g, "awayPoints", "away_points")
        final = bool(_g(g, "completed", default=False)) and hp is not None and ap is not None
        us, them = ((hp, ap) if home else (ap, hp)) if final else (None, None)
        games.append(game(start, home, str(opp).upper(), f"ncaa-{oid}", espn_logo(f"ncaa/500/{oid}") if oid else None,
                          us, them, final, tbd=tbd, tv=tv.get(_g(g, "id")), opp_rank=ranks.get(opp),
                          conf=bool(_g(g, "conferenceGame", "conference_game", default=False))))
    rec = wl(games)
    conf = wl([g for g in games if g["conf"]])
    return dict(record=f"{rec} ({conf})", rank=ranks.get(name),
                logo=(f"ncaa-{t['espn']}", espn_logo(f"ncaa/500/{t['espn']}")), games=games)


# ------------------------------------------------------------------- NHL
_nhl_standings = None


def fetch_nhl(t, today):
    global _nhl_standings
    code, games = t["code"], []
    d = get_json(f"https://api-web.nhle.com/v1/club-schedule-season/{code}/now")
    for g in d.get("games", []):
        if g.get("gameType") not in (2, 3):              # regular season + playoffs
            continue
        home = g["homeTeam"]["abbrev"] == code
        me, op = (g["homeTeam"], g["awayTeam"]) if home else (g["awayTeam"], g["homeTeam"])
        start = dt.datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")).astimezone(ET)
        final = g.get("gameState") in ("OFF", "FINAL")
        nat = [b.get("network") for b in g.get("tvBroadcasts", []) if b.get("market") == "N"]
        oa = op["abbrev"]
        games.append(game(start, home, oa, f"nhl-{oa}", espn_logo(f"nhl/500/{NHL_ESPN.get(oa, oa.lower())}"),
                          me.get("score") if final else None, op.get("score") if final else None, final,
                          tv=nat[0] if nat else None, reg=g.get("gameType") == 2,
                          ot=(g.get("gameOutcome") or {}).get("lastPeriodType") in ("OT", "SO")))
    record = ""
    try:
        if _nhl_standings is None:
            _nhl_standings = get_json("https://api-web.nhle.com/v1/standings/now").get("standings", [])
        for s in _nhl_standings:
            if (s.get("teamAbbrev") or {}).get("default") == code:
                record = f"{s.get('wins', 0)}-{s.get('losses', 0)}-{s.get('otLosses', 0)}"
    except Exception as e:
        print(f"  ! NHL standings: {e}", file=sys.stderr)
    return dict(record=record, rank=None, logo=(f"nhl-{code}", espn_logo(f"nhl/500/{code.lower()}")), games=games)


# ------------------------------------------------------------------- NBA
_nba = None


def fetch_nba(t, today):
    global _nba
    if _nba is None:
        _nba = get_json("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
    code, games = t["code"], []
    for day in _nba["leagueSchedule"]["gameDates"]:
        for g in day["games"]:
            gid = str(g.get("gameId", ""))
            if not gid.startswith(("002", "004")):       # regular season + playoffs
                continue
            ht, at = g["homeTeam"], g["awayTeam"]
            if code not in (ht.get("teamTricode"), at.get("teamTricode")):
                continue
            home = ht["teamTricode"] == code
            me, op = (ht, at) if home else (at, ht)
            start = dt.datetime.fromisoformat(g["gameDateTimeUTC"].replace("Z", "+00:00")).astimezone(ET)
            final = g.get("gameStatus") == 3
            nat = [b.get("broadcasterDisplay") for b in
                   (g.get("broadcasters") or {}).get("nationalBroadcasters", []) or []]
            oa = op.get("teamTricode", "?")
            games.append(game(start, home, oa, f"nba-{oa}", espn_logo(f"nba/500/{NBA_ESPN.get(oa, oa.lower())}"),
                              me.get("score") if final else None, op.get("score") if final else None,
                              final, tv=nat[0] if nat else None, reg=gid.startswith("002")))
    return dict(record=wl(games), rank=None, logo=(f"nba-{code}", espn_logo(f"nba/500/{code.lower()}")), games=games)


# ---------------------------------------------- College hockey / hoops (ESPN)
def _score(c):
    s = c.get("score")
    if isinstance(s, dict):
        s = s.get("value", s.get("displayValue"))
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def fetch_espn_college(t, today, sport):
    d = get_json(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/teams/{t['espn']}/schedule")
    games, rank = [], None
    for ev in d.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        cs = comp.get("competitors", [])
        me = next((c for c in cs if str(c.get("team", {}).get("id")) == t["espn"]), None)
        op = next((c for c in cs if c is not me), None)
        if not me or not op:
            continue
        start = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(ET)
        st = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        final = bool(st.get("completed"))
        ot_ = op.get("team", {})
        logo = (ot_.get("logos") or [{}])[0].get("href") or ot_.get("logo")
        bc = comp.get("broadcasts") or []
        tv = (bc[0].get("media") or {}).get("shortName") if bc else None
        r = (me.get("curatedRank") or {}).get("current")
        if r and r <= 25:
            rank = r
        games.append(game(start, me.get("homeAway") == "home", ot_.get("abbreviation", "?"),
                          f"ncaa-{ot_.get('id')}", logo, _score(me) if final else None,
                          _score(op) if final else None, final,
                          tbd=comp.get("timeValid") is False, tv=tv))
    record = (d.get("team") or {}).get("recordSummary") or wl(games)
    return dict(record=record, rank=rank, logo=(f"ncaa-{t['espn']}", espn_logo(f"ncaa/500/{t['espn']}")), games=games)


FETCH = {
    "nfl": fetch_nfl, "cfb": fetch_cfb, "nhl": fetch_nhl, "nba": fetch_nba,
    "ncaah": lambda t, d: fetch_espn_college(t, d, "hockey/mens-college-hockey"),
    "ncaab": lambda t, d: fetch_espn_college(t, d, "basketball/mens-college-basketball"),
}


# ------------------------------------------------------------- mock data
def mock_data(today):
    ws = today - dt.timedelta(days=today.weekday())

    def at(day, h, m=0):
        return dt.datetime.combine(ws + dt.timedelta(days=day), dt.time(h, m)).replace(tzinfo=ET)

    IDS = {"MINNESOTA": "135", "MICHIGAN": "130", "IOWA": "2294", "PENN STATE": "213", "TOLEDO": "2649",
           "BALL STATE": "2050"}

    def G(start, home, opp, us=None, them=None, tv=None, rank=None, tbd=False):
        key = f"ncaa-{IDS[opp]}" if opp in IDS else f"x-{opp}"
        return game(start, home, opp, key, None, us, them, us is not None, tbd=tbd, tv=tv, opp_rank=rank)

    def L(code):
        return ({"MICH": "ncaa-130", "MINN": "ncaa-135", "WMU": "ncaa-2711"}.get(code, f"x-{code}"), None)

    return {
        "DET-NFL":  dict(record="4-1", rank=None, logo=L("DET"), games=[
            G(at(-1, 13), True, "GB", 27, 20), G(at(6, 13), False, "KC", tv="CBS")]),
        "MIN-NFL":  dict(record="3-2", rank=None, logo=L("MIN"), games=[
            G(at(-1, 13), False, "CHI", 17, 24), G(at(6, 16, 25), True, "PHI", tv="FOX")]),
        "MICH-CFB": dict(record="3-2 (0-2)", rank=None, logo=L("MICH"), games=[
            G(at(-2, 15, 30), False, "MINNESOTA", 14, 20), G(at(12, 12), True, "PENN STATE", tv="FOX", rank=14)]),
        "MINN-CFB": dict(record="4-1 (2-0)", rank=None, logo=L("MINN"), games=[
            G(at(-2, 15, 30), True, "MICHIGAN", 20, 14), G(at(5, 15, 30), False, "IOWA", tv="BTN", rank=18)]),
        "WMU-CFB":  dict(record="3-2 (1-0)", rank=None, logo=L("WMU"), games=[
            G(at(-2, 15, 30), True, "BALL STATE", 31, 17), G(at(5, 15, 30), False, "TOLEDO", tv="ESPN+")]),
        "DET-NHL":  dict(record="1-0-0", rank=None, logo=L("DET"), games=[
            G(at(1, 19), True, "MTL", 4, 2), G(at(3, 19), False, "TOR"), G(at(5, 19), True, "BOS"),
            G(at(6, 17), False, "NYR")]),
        "DET-NBA":  dict(record="0-0", rank=None, logo=L("DET"), games=[
            G(at(2, 19), True, "CHI"), G(at(4, 19, 30), False, "NYK")]),
        "MICH-HKY": dict(record="2-0-0", rank=4, logo=L("MICH"), games=[
            G(at(4, 19), True, "BC"), G(at(5, 19), True, "BC")]),
        "MINN-HKY": dict(record="1-1-0", rank=9, logo=L("MINN"), games=[
            G(at(4, 20), False, "UND"), G(at(5, 19), False, "UND")]),
        "WMU-HKY":  dict(record="2-0-0", rank=2, logo=L("WMU"), games=[
            G(at(4, 19), True, "NMU", ), G(at(5, 18), True, "NMU")]),
    }


# --------------------------------------------------------------- drawing
def font(n, s):
    return ImageFont.truetype(os.path.join(FONTS, n), s)


BIG, MONO, MONOR = "BigShoulders-Bold.ttf", "GeistMono-Bold.ttf", "GeistMono-Regular.ttf"


def tsize(d, s, f):
    b = d.textbbox((0, 0), s, font=f)
    return b[2] - b[0], b


def text_at(d, x, y, s, f, fill, anchor="l"):
    w, b = tsize(d, s, f)
    if anchor == "r":
        x -= w
    elif anchor == "c":
        x -= w // 2
    d.text((x - b[0], y), s, font=f, fill=fill)
    return w


def get_logo(key, url):
    if not key:
        return None
    path = LOGO_OVERRIDE.get(key) or os.path.join(LOGODIR, f"{key}.png")
    if key.startswith("ncaa-") and not os.path.exists(path):
        cached = os.path.join(HERE, "assets", "cfb-logos", key[5:] + ".png")   # from the Michigan wallpaper
        if os.path.exists(cached):
            path = cached
    if not os.path.exists(path) and url:
        os.makedirs(LOGODIR, exist_ok=True)
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            with open(path, "wb") as fh:
                fh.write(r.content)
        except Exception as e:
            print(f"  ! logo {key}: {e}", file=sys.stderr)
            return None
    try:
        return Image.open(path).convert("RGBA") if os.path.exists(path) else None
    except Exception:
        return None


def fit(im, box):
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    s = min(box / im.width, box / im.height)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


def mean_rgb(im):
    sm = im.resize((24, 24)).load()
    tot, n = [0, 0, 0], 0
    for y in range(24):
        for x in range(24):
            r, g, b, a = sm[x, y]
            if a > 80:
                tot[0] += r; tot[1] += g; tot[2] += b; n += 1
    return tuple(v / n for v in tot) if n else (255, 255, 255)


def paste_logo(layer, im, cx, cy, box, bg=(14, 22, 38)):
    """Centered logo; dark marks (Vikings purple, Penn State navy) get a soft light halo."""
    lg = fit(im, box)
    x, y = int(cx - lg.width / 2), int(cy - lg.height / 2)
    r, g, b = mean_rgb(lg)
    if math.dist((r, g, b), bg) < 95:
        pad = 12
        halo = Image.new("RGBA", (lg.width + pad * 2, lg.height + pad * 2), (0, 0, 0, 0))
        shape = Image.new("RGBA", lg.size, (235, 240, 250, 0))
        shape.putalpha(lg.getchannel("A"))
        halo.alpha_composite(shape, (pad, pad))
        halo = halo.filter(ImageFilter.GaussianBlur(8))
        layer.alpha_composite(halo, (x - pad, y - pad))
        layer.alpha_composite(halo, (x - pad, y - pad))
    layer.alpha_composite(lg, (x, y))


def badge(d, cx, cy, size, label, color=(60, 72, 92)):
    r = size // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,), outline=(255, 255, 255, 70), width=2)
    f = font(MONO, max(12, int(size * (0.34 if len(label) <= 3 else 0.26))))
    w, b = tsize(d, label, f)
    d.text((cx - w / 2 - b[0], cy - (b[3] - b[1]) / 2 - b[1]), label, font=f, fill=WHITE + (255,))


def logo_or_badge(layer, d, key, url, label, cx, cy, box, color=(60, 72, 92)):
    im = get_logo(key, url)
    if im:
        paste_logo(layer, im, cx, cy, box)
    else:
        badge(d, cx, cy, int(box * 0.9), label[:4], color)


# ------------------------------------------------------------ background
def make_background():
    """Team-neutral night backdrop: deep navy fade, two cool light pools, faint
    stadium-light streaks, pinstripes and grain. Generated, so nothing to license."""
    top, bot = (16, 26, 46), (4, 6, 12)
    grad = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), bot), Image.new("RGB", (W, H), top), grad).convert("RGBA")

    def glow(cx, cy, rx, ry, rgb, alpha):
        g = Image.radial_gradient("L").resize((rx * 2, ry * 2))
        # PIL's radial gradient hits 181 at the edge midpoints, so fade to 0 by 178
        # (smoothstep) or the pool leaves a hard line where its box ends.
        g = g.point(lambda v: int(alpha * (lambda u: u * u * (3 - 2 * u))(max(0.0, 1 - v / 178))))
        layer = Image.new("RGBA", (W, H), rgb + (0,))
        mask = Image.new("L", (W, H), 0)
        mask.paste(g, (cx - rx, cy - ry))          # paste handles off-canvas offsets cleanly
        layer.putalpha(mask)
        return layer

    img = Image.alpha_composite(img, glow(W // 2, 260, 1100, 900, (60, 105, 170), 150))
    img = Image.alpha_composite(img, glow(1150, 2500, 900, 700, (40, 70, 120), 90))
    img = Image.alpha_composite(img, glow(120, 1500, 700, 900, (30, 60, 100), 60))

    # stadium-light streaks fanning down from the top-left corner
    rays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rays)
    random.seed(7)
    for i in range(9):
        ang = math.radians(28 + i * 6.5 + random.uniform(-1.5, 1.5))
        x2, y2 = -200 + math.cos(ang) * 4200, -300 + math.sin(ang) * 4200
        rd.line([(-200, -300), (x2, y2)], fill=(170, 200, 255, random.randint(14, 26)),
                width=random.randint(40, 110))
    img = Image.alpha_composite(img, rays.filter(ImageFilter.GaussianBlur(40)))

    # fine diagonal pinstripes
    pin = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pin)
    for k in range(-H, W, 16):
        pd.line([(k, 0), (k + H, H)], fill=(255, 255, 255, 7), width=1)
    img = Image.alpha_composite(img, pin)

    # vignette
    vig = Image.radial_gradient("L").resize((int(W * 1.6), int(H * 1.25)))
    vig = vig.crop(((vig.width - W) // 2, (vig.height - H) // 2,
                    (vig.width - W) // 2 + W, (vig.height - H) // 2 + H))
    vig = vig.point(lambda v: int(max(0, v - 120) * 1.3))
    img = Image.alpha_composite(img, Image.merge("RGBA", (*[Image.new("L", (W, H), 0)] * 3, vig)))

    # grain
    # (no film grain: it made every render a ~3.3 MB PNG; without it ~0.5 MB)
    return img


def backdrop():
    if os.path.exists(BG_IMAGE):
        im = Image.open(BG_IMAGE).convert("RGBA")
        if im.size != (W, H):
            s = max(W / im.width, H / im.height)
            im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
            ox, oy = (im.width - W) // 2, (im.height - H) // 2
            im = im.crop((ox, oy, ox + W, oy + H))
        return im
    return make_background()


# ---------------------------------------------------------------- render
MON = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
DOW = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def clock(t, short=False):
    h = t.strftime("%-I")
    m = t.strftime("%M")
    ap = t.strftime("%p")
    if short:
        return f"{h}{'' if m == '00' else ':' + m}{ap[0]}"
    return f"{h}:{m} {ap}"


def when(g, today):
    d = g["dt"].date()
    delta = (d - today).days
    day = "TODAY" if delta == 0 else (DOW[d.weekday()] if 0 < delta < 7 else f"{MON[d.month]} {d.day}")
    return f"{day}  {'TBD' if g['tbd'] else clock(g['dt'])}"


def result(g):
    if g["us"] > g["them"]:
        return "W", WINC
    if g["us"] < g["them"]:
        return "L", LOSSC
    return "T", DIM


def opp_label(g):
    rk = f"#{g['opp_rank']} " if g.get("opp_rank") else ""
    return f"{'vs' if g['home'] else '@'} {rk}{g['opp']}"


def build(cards, rows, today, mock=False):
    img = backdrop()
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ws = today - dt.timedelta(days=today.weekday())
    we = ws + dt.timedelta(days=6)

    # ---- sizing: football cards are fixed and compact; the nightly grid gets the rest
    HDR, SEC, FOOT = 92, 40, 58
    card_h, card_gap = 116, 12
    day_h, row_gap = 78, 10
    avail = BAND_BOT - BAND_TOP
    used = HDR + FOOT + (len(cards) * (card_h + card_gap) - card_gap if cards else 0)
    row_h = 0
    if rows:
        room = avail - used - SEC - day_h
        row_h = int(min(172, max(92, (room + row_gap) / len(rows) - row_gap)))
    total = used + ((SEC + day_h + len(rows) * (row_h + row_gap) - row_gap) if rows else 0)
    y = BAND_TOP + max(0, (avail - total) // 2)

    # ---- header
    title = f"WEEK OF {MON[ws.month]} {ws.day} – " + (f"{we.day}" if we.month == ws.month else f"{MON[we.month]} {we.day}")
    text_at(d, W // 2, y + 6, title, font(MONO, 34), WHITE + (235,), "c")
    tw_, _ = tsize(d, title, font(MONO, 34))
    for side in (-1, 1):
        x_in, x_out = W // 2 + side * (tw_ // 2 + 28), W // 2 + side * (tw_ // 2 + 190)
        d.line([(min(x_in, x_out), y + 27), (max(x_in, x_out), y + 27)], fill=(255, 255, 255, 60), width=2)
    y += HDR

    # ---- football cards (compact)
    f_name, f_rec, f_lbl = font(BIG, 48), font(MONOR, 22), font(MONO, 17)
    f_res, f_when, f_opp, f_rank = font(MONO, 22), font(BIG, 40), font(MONO, 21), font(MONO, 25)
    OL = 34                                            # opponent logo size on the cards
    for t, info in cards:
        x, h = X0, card_h
        d.rounded_rectangle([x, y, X1, y + h], radius=18, fill=(10, 16, 30, 150), outline=(255, 255, 255, 26), width=2)
        d.rounded_rectangle([x, y + 9, x + 8, y + h - 9], radius=4, fill=t["color"] + (255,))
        lk, lu = info["logo"]
        logo_or_badge(layer, d, lk, lu, t["name"][:4], x + 66, y + h // 2, 76, t["color"])

        nx, ny = x + 122, y + 10
        if info.get("rank"):
            nx += text_at(d, nx, ny + 15, f"#{info['rank']}", f_rank, GOLD + (255,)) + 9
        nx += text_at(d, nx, ny, t["name"], f_name, WHITE + (255,)) + 14
        if info.get("record"):
            text_at(d, nx, ny + 18, info["record"], f_rec, DIM + (255,))

        games = sorted(info["games"], key=lambda g: g["dt"])
        last = next((g for g in reversed(games) if g["final"]), None)
        nxt = next((g for g in games if not g["final"] and g["dt"] >= dt.datetime.now(ET) - dt.timedelta(hours=5)), None)
        if mock:
            nxt = next((g for g in games if not g["final"]), None)

        ly = y + 70                                    # second line (text top)
        lc = ly + 13                                   # its vertical centre, for logos
        lx = x + 122
        if last:
            lx += text_at(d, lx, ly + 3, "LAST", f_lbl, DIM + (200,)) + 12
            r, col = result(last)
            lx += text_at(d, lx, ly, f"{r} {last['us']}-{last['them']}", f_res, col + (255,)) + 12
            lx += text_at(d, lx, ly + 1, "vs" if last["home"] else "@", f_opp, DIM + (255,)) + 8
            logo_or_badge(layer, d, last["logo_key"], last["logo_url"], last["opp"], lx + OL // 2, lc, OL)
            text_at(d, lx + OL + 8, ly + 1, last["opp"], f_opp, (215, 222, 232, 235))

        rx = X1 - 24
        if nxt and ws <= nxt["dt"].date() <= we:
            is_today = nxt["dt"].date() == today
            text_at(d, rx, y + 10, when(nxt, today), f_when, (GOLD if is_today else WHITE) + (255,), "r")
            ox = rx
            if nxt.get("tv"):
                ox -= text_at(d, ox, ly + 1, nxt["tv"], f_opp, GOLD + (230,), "r") + 14
            rk = f"#{nxt['opp_rank']} " if nxt.get("opp_rank") else ""
            ox -= text_at(d, ox, ly + 1, rk + nxt["opp"], f_opp, WHITE + (240,), "r") + 8
            logo_or_badge(layer, d, nxt["logo_key"], nxt["logo_url"], nxt["opp"], ox - OL // 2, lc, OL)
            text_at(d, ox - OL - 8, ly + 1, "vs" if nxt["home"] else "@", f_opp, DIM + (255,), "r")
        elif nxt:
            text_at(d, rx, y + 10, "BYE WEEK", f_when, (200, 208, 220, 255), "r")
            rk = f"#{nxt['opp_rank']} " if nxt.get("opp_rank") else ""
            ox = rx - text_at(d, rx, ly + 1, rk + nxt["opp"], f_opp, DIM + (255,), "r") - 8
            logo_or_badge(layer, d, nxt["logo_key"], nxt["logo_url"], nxt["opp"], ox - OL // 2, lc, OL)
            text_at(d, ox - OL - 8, ly + 1, f"{MON[nxt['dt'].month]} {nxt['dt'].day}  {'vs' if nxt['home'] else '@'}",
                    f_opp, DIM + (255,), "r")
        else:
            text_at(d, rx, y + 10, "SEASON OVER", f_when, DIM + (255,), "r")
        y += h + card_gap

    # ---- nightly grid (bigger; scales with however many rows this week has)
    if rows:
        y += SEC - card_gap
        k = row_h / 160                                # 1.0 at full size
        label_w = 272
        cw = (X1 - X0 - label_w) / 7
        strip_top = y
        strip_bot = y + day_h + len(rows) * (row_h + row_gap) - row_gap
        ti = (today - ws).days
        tx0 = int(X0 + label_w + ti * cw)
        f_dow, f_day = font(MONO, 22), font(BIG, 42)
        for i in range(7):
            dd = ws + dt.timedelta(days=i)
            cx = X0 + label_w + i * cw + cw / 2
            text_at(d, cx, y + 2, DOW[i], f_dow, (GOLD if i == ti else DIM) + (255,), "c")
            text_at(d, cx, y + 28, str(dd.day), f_day, (GOLD if i == ti else WHITE) + (255,), "c")
        y += day_h

        f_rn = font(BIG, int(46 * max(k, 0.8)))
        f_sub = font(MONOR, int(22 * max(k, 0.85)))
        f_cell = font(MONO, int(28 * max(k, 0.8)))
        f_cell_sm = font(MONO, int(22 * max(k, 0.8)))
        cell_logo = int(70 * k)
        for t, info in rows:
            h = row_h
            d.rounded_rectangle([X0, y, X1, y + h], radius=18, fill=(10, 16, 30, 140), outline=(255, 255, 255, 22), width=2)
            d.rounded_rectangle([X0, y + 12, X0 + 8, y + h - 12], radius=4, fill=t["color"] + (255,))
            lk, lu = info["logo"]
            logo_or_badge(layer, d, lk, lu, t["name"][:4], X0 + 62, y + h // 2, int(84 * k), t["color"])
            tx = X0 + 62 + int(84 * k) // 2 + 14
            name_h = tsize(d, "M", f_rn)[1]
            text_at(d, tx, y + int(h * 0.20), t["name"], f_rn, WHITE + (255,))
            sub = " · ".join(v for v in (t.get("sub"), f"#{info['rank']}" if info.get("rank") else None,
                                          info.get("record")) if v)
            text_at(d, tx, y + int(h * 0.58), sub, f_sub, DIM + (255,))

            byday = {}
            for g in info["games"]:
                if ws <= g["dt"].date() <= we:
                    byday.setdefault((g["dt"].date() - ws).days, g)
            for i, g in byday.items():
                c0 = X0 + label_w + i * cw
                box = [int(c0) + 6, y + 7, int(c0 + cw) - 6, y + h - 7]
                if g["home"]:
                    d.rounded_rectangle(box, radius=14, fill=t["color"] + (62,), outline=t["color"] + (160,), width=2)
                else:
                    d.rounded_rectangle(box, radius=14, fill=(255, 255, 255, 8), outline=(255, 255, 255, 60), width=2)
                cx = c0 + cw / 2
                logo_or_badge(layer, d, g["logo_key"], g["logo_url"], g["opp"], cx, y + int(h * 0.38), cell_logo)
                if g["final"]:
                    r, col = result(g)
                    txt, fill = f"{r} {g['us']}-{g['them']}", col
                else:
                    txt, fill = ("TBD" if g["tbd"] else clock(g["dt"], short=True)), WHITE
                fc = f_cell if tsize(d, txt, f_cell)[0] < cw - 16 else f_cell_sm
                text_at(d, cx, y + int(h * 0.70), txt, fc, fill + (255,), "c")
            y += h + row_gap
        y -= row_gap
        # today's column, drawn last so it sits over the rows
        hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(hl).rounded_rectangle([tx0 + 2, strip_top - 8, int(tx0 + cw) - 2, strip_bot + 8],
                                             radius=16, fill=(255, 255, 255, 14), outline=GOLD + (150,), width=2)
        layer.alpha_composite(hl)

    # ---- footer
    stamp = f"{DOW[today.weekday()]} {today.month}/{today.day}"   # date only: a minute stamp made every run a new commit
    foot_txt = "TINTED = HOME   ·   ALL TIMES ET   ·   " + ("SAMPLE DATA" if mock else f"UPDATED {stamp}")
    text_at(d, W // 2, y + 24, foot_txt, font(MONOR, 20), (255, 255, 255, 120), "c")

    img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


def active(info, today):
    """Show a football card only while that team's season is on (within 3 weeks of a game)."""
    return any(abs((g["dt"].date() - today).days) <= 21 for g in info["games"])


def main():
    mock = "--mock" in sys.argv
    today = (dt.date.fromisoformat(os.environ["LOOKAHEAD_DATE"]) if os.environ.get("LOOKAHEAD_DATE")
             else dt.datetime.now(ET).date())
    ws = today - dt.timedelta(days=today.weekday())
    we = ws + dt.timedelta(days=6)
    sample = mock_data(today) if mock else {}

    data = []
    for t in TEAMS:
        try:
            info = sample[t["key"]] if mock else FETCH[t["league"]](t, today)
        except KeyError:
            continue
        except Exception as e:
            print(f"  ! {t['key']}: {e}", file=sys.stderr)
            continue
        data.append((t, info))
        print(f"  {t['key']:9} {len(info['games']):3} games  {info.get('record', '')}")

    cards = [(t, i) for t, i in data if t["kind"] == "card" and active(i, today)]
    rows = [(t, i) for t, i in data if t["kind"] == "strip"
            and any(ws <= g["dt"].date() <= we for g in i["games"])]
    print(f"week {ws} – {we}: {len(cards)} football cards, {len(rows)} nightly rows")

    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "lookahead.png")
    build(cards, rows, today, mock).save(out)
    print("->", out)


if __name__ == "__main__":
    if "--make-background" in sys.argv:
        os.makedirs(os.path.dirname(BG_IMAGE), exist_ok=True)
        make_background().convert("RGB").save(BG_IMAGE)
        print("->", BG_IMAGE)
    else:
        main()
