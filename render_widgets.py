#!/usr/bin/env python3
"""
Renders home-screen WIDGET images alongside the full wallpaper.

Outputs into output/:
    widget-next.png      medium widget (1092x510)  - the next 4 games
    widget-month.png     large  widget (1092x1146) - the month currently in play
    widget-<month>.png   large  widget per month with games (july, august, ...)

The per-month files exist so you can build a swipeable Smart Stack: point each
Scriptable widget at a different one via its Parameter field.

Run after (or instead of) render_wallpaper.py. Shares its data + assets.
"""

import os, math, datetime as dt
from PIL import Image, ImageDraw, ImageFilter

import render_wallpaper as rw          # reuse fetch, logos, fonts, colors

OUTDIR = rw.OUTDIR
NAVY, ORANGE, WHITE = rw.NAVY, rw.ORANGE, rw.WHITE
font, logo, fade, fit = rw.font, rw.logo, rw.fade, rw.fit
MONTHS = rw.MONTHS


def backdrop(w, h, det):
    """Dark navy field with an orange bloom bottom-right, plus a ghosted D."""
    bg = Image.new("RGB", (w, h), (5, 7, 11))
    px = bg.load()
    cx, cy = w * 0.5, h * 1.05
    for y in range(h):
        for x in range(0, w, 2):
            g = max(0.0, 1.0 - math.hypot((x - cx) / (w * 1.05), (y - cy) / (h * 1.15))) ** 1.6
            c = (min(255, int(5 + NAVY[0] * g * 3.0)),
                 min(255, int(7 + NAVY[1] * g * 3.0)),
                 min(255, int(11 + NAVY[2] * g * 3.0)))
            px[x, y] = c
            if x + 1 < w:
                px[x + 1, y] = c
    im = bg.filter(ImageFilter.GaussianBlur(2)).convert("RGBA")
    gh = fade(fit(det, int(h * 0.85), int(h * 0.85)), 26)
    im.alpha_composite(gh, (w - gh.width + int(h * 0.10), h - gh.height + int(h * 0.06)))
    return im


def card(cards, cd, x, y, cw, ch, g, today, day_size, meta_size, pad):
    """One game card: day number, W/L or time, opponent logo, home/away bar."""
    done = g["state"] == "Final"
    a = 132 if done else 255
    cd.rectangle([x, y, x + cw, y + ch], outline=(255, 255, 255, int(a * 0.55)), width=2)

    df = font("BigShoulders-Bold.ttf", day_size)
    cd.text((x + pad, y + int(day_size * 0.02)), str(g["day"]), font=df, fill=(255, 255, 255, a))

    if done and g["res"]:
        txt, f = g["res"], font("GeistMono-Bold.ttf", meta_size + 2)
    else:
        txt, f = g["time"], font("GeistMono-Regular.ttf", meta_size)
    bb = cd.textbbox((0, 0), txt, font=f)
    cd.text((x + cw - pad - (bb[2] - bb[0]) - bb[0], y + int(day_size * 0.26)), txt, font=f,
            fill=(ORANGE + (240,)) if g["res"] == "W" else (255, 255, 255, a))

    top = int(day_size * 1.08)
    barh = max(7, int(ch * 0.045))
    lh = ch - top - barh - int(ch * 0.09)
    lw = int(cw * 0.68)
    lg = fade(fit(logo(g["opp"]), lw, lh), a)
    cards.alpha_composite(lg, (x + (cw - lg.width) // 2, y + top + (lh - lg.height) // 2))

    cd.rectangle([x + pad, y + ch - int(ch * 0.055) - barh, x + cw - pad, y + ch - int(ch * 0.055)],
                 fill=(ORANGE if g["home"] else WHITE) + (a,))
    if g["date"] == today:
        cd.rectangle([x - 4, y - 4, x + cw + 4, y + ch + 4], outline=ORANGE + (240,), width=3)


def render_next(games, det, path, n=4):
    """Medium widget: the next n games not yet final."""
    W, H = 1092, 510
    today = dt.date.today()
    up = sorted((g for g in games if g["date"] >= today), key=lambda g: (g["date"], g["time"]))[:n]
    if not up:
        up = sorted(games, key=lambda g: g["date"])[-n:]

    img = backdrop(W, H, det)
    d = ImageDraw.Draw(img)
    hf = font("BigShoulders-Bold.ttf", 46)
    d.text((28, 16), "NEXT UP", font=hf, fill=(255, 255, 255, 210))
    lf = font("GeistMono-Regular.ttf", 20)
    lab = "ET"
    bb = d.textbbox((0, 0), lab, font=lf)
    d.text((W - 28 - (bb[2] - bb[0]) - bb[0], 30), lab, font=lf, fill=(255, 255, 255, 120))

    M, GAP = 26, 18
    cw = (W - 2 * M - (len(up) - 1) * GAP) // max(1, len(up))
    ch = 372
    top = 96
    cards = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cards)
    for i, g in enumerate(up):
        card(cards, cd, M + i * (cw + GAP), top, cw, ch, g, today, 60, 26, 12)
    Image.alpha_composite(img, cards).convert("RGB").save(path)
    return len(up)


def render_month(games, det, year, month, path):
    """Large widget: full month grid."""
    W, H = 1092, 1146
    today = dt.date.today()
    mg = sorted((g for g in games if g["month"] == month and g["date"].year == year),
                key=lambda g: (g["date"], g["time"]))
    img = backdrop(W, H, det)
    d = ImageDraw.Draw(img)

    label = MONTHS[month]
    size = 82 if len(label) <= 8 else 66
    mf = font("BigShoulders-Bold.ttf", size)
    d.text((28, 14), label, font=mf, fill=(0, 0, 0, 0),
           stroke_width=3, stroke_fill=(255, 255, 255, 190))
    yf = font("GeistMono-Bold.ttf", 24)
    bb = d.textbbox((0, 0), str(year), font=yf)
    d.text((W - 28 - (bb[2] - bb[0]) - bb[0], 44), str(year), font=yf, fill=ORANGE + (215,))

    COLS, M, GAP, RGAP = 5, 24, 14, 14
    TOP, BOT = 112, 34
    cw = (W - 2 * M - (COLS - 1) * GAP) // COLS
    rows = max(1, math.ceil(len(mg) / COLS))
    ch = min(210, (H - TOP - BOT - (rows - 1) * RGAP) // rows)

    cards = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cards)
    for i, g in enumerate(mg):
        r, c = divmod(i, COLS)
        card(cards, cd, M + c * (cw + GAP), TOP + r * (ch + RGAP), cw, ch, g, today, 48, 20, 10)
    Image.alpha_composite(img, cards).convert("RGB").save(path)
    return len(mg), rows


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    games = rw.fetch_games(rw.SEASON)
    det = logo("DET")

    n = render_next(games, det, os.path.join(OUTDIR, "widget-next.png"))
    print(f"widget-next.png    {n} games")

    year, month = rw.pick_month(games)
    cnt, rows = render_month(games, det, year, month, os.path.join(OUTDIR, "widget-month.png"))
    print(f"widget-month.png   {MONTHS[month].title()} {year}: {cnt} games, {rows} rows")

    for y, m in sorted({(g["date"].year, g["month"]) for g in games}):
        name = f"widget-{MONTHS[m].lower()}.png"
        cnt, rows = render_month(games, det, y, m, os.path.join(OUTDIR, name))
        print(f"{name:18} {MONTHS[m].title()} {y}: {cnt} games, {rows} rows")


if __name__ == "__main__":
    main()
