"""Generate 10 branded promo images for the Discord Music Bot.

All icons are drawn as PIL vector shapes (no emoji glyphs) so they render
crisp on every system. Arabic is shaped natively by libraqm.
Output: assets/promo/*.png at 1280x640 (GitHub-card friendly).
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
OUT = os.path.join(HERE, "promo")
os.makedirs(OUT, exist_ok=True)

W, H = 1280, 640

# --- Brand palette --------------------------------------------------------- #
NAVY = (10, 14, 39)
RED = (232, 0, 28)
GOLD = (212, 168, 67)
BLURPLE = (88, 101, 242)
CARD = (20, 26, 58)
CARD_HI = (28, 36, 78)
LINE = (38, 48, 94)
MUTED = (154, 166, 212)
DIM = (118, 130, 175)
WHITE = (255, 255, 255)
GREEN = (87, 242, 135)
BLUE = (66, 153, 245)
PURPLE = (163, 113, 247)
PINK = (236, 84, 178)


def has_ar(s: str) -> bool:
    return any("؀" <= c <= "ۿ" or "ݐ" <= c <= "ݿ" for c in s)


def _kw(s: str) -> dict:
    return dict(direction="rtl", language="ar") if has_ar(s) else {}


def inter(size: int, weight: int = 700):
    f = ImageFont.truetype(os.path.join(FONTS, "Inter-var.ttf"), size)
    try:
        f.set_variation_by_axes([14, weight])
    except Exception:
        pass
    return f


def taj(size: int, bold=True):
    name = "Tajawal-ExtraBold.ttf" if bold else "Tajawal-Bold.ttf"
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def T(d, xy, s, font, fill, anchor="la"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor, **_kw(s))


def tw(d, s, font):
    b = d.textbbox((0, 0), s, font=font, **_kw(s))
    return b[2] - b[0], b[3] - b[1]


def base(glow1=RED, glow2=BLURPLE):
    img = Image.new("RGB", (W, H), NAVY)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.45, -H * 0.5, W * 1.15, H * 0.6], fill=glow1 + (95,))
    gd.ellipse([-W * 0.25, H * 0.35, W * 0.45, H * 1.25], fill=glow2 + (75,))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    return Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")


def card(d, xy, fill=CARD, outline=LINE, radius=22, width=2):
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def dot(d, cx, cy, r, fill):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


# --------------------------------------------------------------------------- #
#  Vector icons — drawn so they don't depend on emoji glyphs
# --------------------------------------------------------------------------- #
def icon_note(d, cx, cy, scale, color):
    """Eighth-note: filled note head + vertical stem + flag."""
    # head
    r = int(scale * 0.32)
    hx, hy = cx - int(scale * 0.18), cy + int(scale * 0.36)
    d.ellipse([hx - r, hy - r // 1, hx + r, hy + r // 1], fill=color)
    # stem
    sx1, sy1 = hx + r - 4, hy
    sx2, sy2 = sx1 + 6, hy - int(scale * 0.95)
    d.rounded_rectangle([sx1, sy2, sx2, sy1], radius=2, fill=color)
    # flag
    fx = sx2
    fy = sy2
    d.polygon([(fx, fy), (fx + int(scale * 0.35), fy + int(scale * 0.18)),
               (fx + int(scale * 0.30), fy + int(scale * 0.45)),
               (fx + 2, fy + int(scale * 0.25))], fill=color)


def icon_play(d, cx, cy, scale, color):
    s = scale
    d.polygon([(cx - s // 3, cy - s // 2),
               (cx - s // 3, cy + s // 2),
               (cx + s // 2, cy)], fill=color)


def icon_pause(d, cx, cy, scale, color):
    bw = max(4, scale // 5)
    bh = scale
    gap = scale // 4
    d.rounded_rectangle([cx - gap - bw, cy - bh // 2, cx - gap, cy + bh // 2],
                        radius=3, fill=color)
    d.rounded_rectangle([cx + gap, cy - bh // 2, cx + gap + bw, cy + bh // 2],
                        radius=3, fill=color)


def icon_playpause(d, cx, cy, scale, color):
    """Combined play + pause symbol — slim triangle + a single bar."""
    s = scale
    d.polygon([(cx - s // 2, cy - s // 2),
               (cx - s // 2, cy + s // 2),
               (cx, cy)], fill=color)
    bw = max(4, s // 6)
    d.rounded_rectangle([cx + s // 6, cy - s // 2, cx + s // 6 + bw, cy + s // 2],
                        radius=3, fill=color)


def icon_skip(d, cx, cy, scale, color):
    """Two triangles + a vertical bar."""
    s = scale
    d.polygon([(cx - s // 2, cy - s // 2), (cx - s // 2, cy + s // 2),
               (cx - s // 8, cy)], fill=color)
    d.polygon([(cx - s // 8, cy - s // 2), (cx - s // 8, cy + s // 2),
               (cx + s // 4, cy)], fill=color)
    bw = max(4, s // 8)
    d.rounded_rectangle([cx + s // 4 + 6, cy - s // 2,
                         cx + s // 4 + 6 + bw, cy + s // 2],
                        radius=2, fill=color)


def icon_stop(d, cx, cy, scale, color):
    s = scale
    d.rounded_rectangle([cx - s // 2, cy - s // 2, cx + s // 2, cy + s // 2],
                        radius=4, fill=color)


def icon_loop(d, cx, cy, scale, color):
    """A circular arc with a single arrowhead."""
    s = scale
    r = s // 2
    box = [cx - r, cy - r, cx + r, cy + r]
    # Arc from 30° to 320° (leaves an opening on the right)
    d.arc(box, start=20, end=320, fill=color, width=max(4, s // 9))
    # Arrowhead at the start of the arc (top-right area)
    a = math.radians(330)
    ax, ay = cx + r * math.cos(a), cy + r * math.sin(a)
    d.polygon([(ax - 8, ay - 12), (ax + 12, ay), (ax - 8, ay + 12)], fill=color)


def icon_shuffle(d, cx, cy, scale, color):
    """Two crossing arrows — quick stylized cross."""
    s = scale
    w = max(4, s // 9)
    # Top-left → bottom-right
    d.line([(cx - s // 2, cy - s // 3), (cx + s // 2, cy + s // 3)],
           fill=color, width=w)
    d.polygon([(cx + s // 2 - 2, cy + s // 3 - 10),
               (cx + s // 2 + 8, cy + s // 3),
               (cx + s // 2 - 2, cy + s // 3 + 10)], fill=color)
    # Bottom-left → top-right
    d.line([(cx - s // 2, cy + s // 3), (cx + s // 2, cy - s // 3)],
           fill=color, width=w)
    d.polygon([(cx + s // 2 - 2, cy - s // 3 - 10),
               (cx + s // 2 + 8, cy - s // 3),
               (cx + s // 2 - 2, cy - s // 3 + 10)], fill=color)


def icon_queue(d, cx, cy, scale, color):
    """Three stacked horizontal bars (a list)."""
    s = scale
    h = max(4, s // 7)
    gap = h + max(4, s // 7)
    w = s
    for i, off in enumerate([-gap, 0, gap]):
        d.rounded_rectangle([cx - w // 2, cy + off - h // 2,
                             cx + w // 2, cy + off + h // 2],
                            radius=3, fill=color)


def icon_plus(d, cx, cy, scale, color):
    s = scale
    w = max(4, s // 5)
    d.rounded_rectangle([cx - s // 2, cy - w // 2, cx + s // 2, cy + w // 2],
                        radius=3, fill=color)
    d.rounded_rectangle([cx - w // 2, cy - s // 2, cx + w // 2, cy + s // 2],
                        radius=3, fill=color)


def icon_check(d, cx, cy, scale, color):
    s = scale
    w = max(4, s // 7)
    d.line([(cx - s // 2, cy), (cx - s // 8, cy + s // 3),
            (cx + s // 2, cy - s // 2)], fill=color, width=w)


def icon_cross(d, cx, cy, scale, color):
    s = scale
    w = max(4, s // 6)
    d.line([(cx - s // 2, cy - s // 2), (cx + s // 2, cy + s // 2)],
           fill=color, width=w)
    d.line([(cx - s // 2, cy + s // 2), (cx + s // 2, cy - s // 2)],
           fill=color, width=w)


def icon_warn(d, cx, cy, scale, color):
    """Triangle warning."""
    s = scale
    d.polygon([(cx, cy - s // 2), (cx - s // 2, cy + s // 2),
               (cx + s // 2, cy + s // 2)], outline=color, fill=None, width=4)
    # Exclamation bar
    bw = max(3, s // 12)
    d.rounded_rectangle([cx - bw // 2, cy - s // 8,
                         cx + bw // 2, cy + s // 5], radius=2, fill=color)
    d.ellipse([cx - bw // 2, cy + s // 4, cx + bw // 2, cy + s // 4 + bw],
              fill=color)


def icon_link(d, cx, cy, scale, color):
    """Two interlocking ovals."""
    s = scale
    w = max(4, s // 8)
    d.rounded_rectangle([cx - s // 2, cy - s // 5,
                         cx + s // 8, cy + s // 5],
                        radius=s // 4, outline=color, width=w, fill=None)
    d.rounded_rectangle([cx - s // 8, cy - s // 5,
                         cx + s // 2, cy + s // 5],
                        radius=s // 4, outline=color, width=w, fill=None)


def icon_box(d, cx, cy, scale, color):
    """Mailbox-like square outline (used for 'empty queue' implication)."""
    s = scale
    d.rounded_rectangle([cx - s // 2, cy - s // 2,
                         cx + s // 2, cy + s // 2],
                        radius=6, outline=color, width=4, fill=None)


def chip(d, xy, label, font, fill_bg, fill_fg, pad_x=18, pad_y=10, radius=18,
         leading_dot=None):
    """Pill chip with text + optional leading colored dot."""
    x, y = xy
    pre = 0
    if leading_dot is not None:
        pre = 22
    tw_, th_ = tw(d, label, font)
    w = tw_ + pad_x * 2 + pre
    h = th_ + pad_y * 2
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill_bg)
    if leading_dot is not None:
        dot(d, x + pad_x + 8, y + h // 2, 6, leading_dot)
    T(d, (x + pad_x + pre, y + pad_y - 2), label, font, fill_fg)
    return w, h


def save(img, name):
    p = os.path.join(OUT, name)
    img.save(p, "PNG", optimize=True)
    print(f"  wrote {p}  ({os.path.getsize(p) // 1024} KB)")


# --------------------------------------------------------------------------- #
#  1. HERO
# --------------------------------------------------------------------------- #
def hero():
    img = base()
    d = ImageDraw.Draw(img)

    # Mark: red rounded square with a drawn music note
    mx, my, ms = 90, 220, 200
    d.rounded_rectangle([mx, my, mx + ms, my + ms], radius=44, fill=RED,
                        outline=GOLD, width=4)
    icon_note(d, mx + ms // 2 - 6, my + ms // 2 - 6, 130, WHITE)

    f_title = inter(96, 900)
    f_sub = inter(38, 600)
    f_taj = taj(34)
    f_pill = inter(22, 700)

    T(d, (340, 200), "Music Bot", f_title, WHITE)
    T(d, (340, 305), "cookie-free YouTube · for Discord", f_sub, MUTED)
    T(d, (340, 360), "بث يوتيوب مباشر داخل الروم الصوتي", f_taj, GOLD)

    chips = [
        ("direct MP3 stream",  GREEN,  NAVY,  NAVY),
        ("no login · no cookies", BLUE, WHITE, WHITE),
        ("Arabic + English",   GOLD,   NAVY,  NAVY),
        ("playlists · queue",  PURPLE, WHITE, WHITE),
    ]
    x = 340
    for label, bg, fg, dotc in chips:
        w, h = chip(d, (x, 460), label, f_pill, bg, fg,
                    pad_x=20, pad_y=12, radius=22, leading_dot=dotc)
        x += w + 12

    T(d, (W // 2, H - 38),
      "github.com/khaledq84ever/discord-music-bot",
      inter(20, 500), DIM, anchor="mm")
    save(img, "01-hero.png")


# --------------------------------------------------------------------------- #
#  2. COMMANDS GRID
# --------------------------------------------------------------------------- #
def commands():
    img = base(glow1=BLURPLE, glow2=RED)
    d = ImageDraw.Draw(img)
    T(d, (60, 50), "Slash Commands", inter(56, 900), WHITE)
    T(d, (60, 120), "12 commands · all in one bot", inter(26, 500), MUTED)

    cmds = [
        ("/play",       "URL or search words",  RED),
        ("/skip",       "next track",           BLUE),
        ("/pause",      "pause playback",       GOLD),
        ("/resume",     "resume playback",      GREEN),
        ("/queue",      "show the queue",       PURPLE),
        ("/nowplaying", "what's playing",       PINK),
        ("/volume",     "0 – 200 %",            BLUE),
        ("/loop",       "repeat one",           GOLD),
        ("/shuffle",    "shuffle queue",        GREEN),
        ("/stop",       "stop & leave",         RED),
        ("/leave",      "leave voice",          PURPLE),
        ("/help",       "show all commands",    PINK),
    ]
    col_w, row_h, gap = 280, 100, 16
    x0, y0 = 60, 180
    f_cmd = inter(26, 800)
    f_desc = inter(18, 500)
    for i, (name, desc, accent) in enumerate(cmds):
        r, c = divmod(i, 4)
        x = x0 + c * (col_w + gap)
        y = y0 + r * (row_h + gap)
        card(d, [x, y, x + col_w, y + row_h])
        d.rounded_rectangle([x, y, x + 8, y + row_h], radius=4, fill=accent)
        T(d, (x + 24, y + 22), name, f_cmd, WHITE)
        T(d, (x + 24, y + 60), desc, f_desc, MUTED)
    save(img, "02-commands.png")


# --------------------------------------------------------------------------- #
#  3. BUTTON INTERFACE
# --------------------------------------------------------------------------- #
def buttons():
    img = base(glow1=GOLD, glow2=RED)
    d = ImageDraw.Draw(img)
    T(d, (60, 50), "One-tap controls", inter(56, 900), WHITE)
    T(d, (60, 120), "buttons attached to every now-playing message",
      inter(24, 500), MUTED)
    T(d, (60, 158), "أزرار تحكّم  مباشرة على رسالة التشغيل", taj(26), GOLD)

    btns = [
        ("play / pause", CARD_HI, WHITE, icon_playpause),
        ("skip",         CARD_HI, WHITE, icon_skip),
        ("loop",         CARD_HI, WHITE, icon_loop),
        ("shuffle",      CARD_HI, WHITE, icon_shuffle),
        ("queue",        BLURPLE, WHITE, icon_queue),
        ("stop",         RED,     WHITE, icon_stop),
    ]
    bw, bh, gap = 170, 140, 22
    total = len(btns) * bw + (len(btns) - 1) * gap
    x = (W - total) // 2
    y = 250
    f_label = inter(20, 600)
    for label, bg, fg, draw_icon in btns:
        d.rounded_rectangle([x, y, x + bw, y + bh], radius=24, fill=bg,
                            outline=LINE, width=2)
        draw_icon(d, x + bw // 2, y + 54, 56, fg)
        T(d, (x + bw // 2, y + 110), label, f_label, MUTED, anchor="mm")
        x += bw + gap

    T(d, (W // 2, 480),
      "only listeners in the same voice channel can press",
      inter(22, 500), DIM, anchor="mm")
    T(d, (W // 2, 520),
      "محصور على من في نفس الروم الصوتي", taj(24), DIM, anchor="mm")
    save(img, "03-buttons.png")


# --------------------------------------------------------------------------- #
#  4. NOW-PLAYING EMBED MOCKUP
# --------------------------------------------------------------------------- #
def now_playing():
    img = base(glow1=RED, glow2=PURPLE)
    d = ImageDraw.Draw(img)
    T(d, (60, 50), "Now Playing", inter(56, 900), WHITE)
    T(d, (60, 120),
      "live embed with thumbnail, channel, length, requester",
      inter(22, 500), MUTED)

    mx, my, mw, mh = 90, 190, W - 180, 380
    card(d, [mx, my, mx + mw, my + mh],
         fill=(32, 34, 47), outline=(40, 42, 60), radius=18)
    d.rounded_rectangle([mx, my, mx + 6, my + mh], radius=3, fill=RED)

    # Header row: note icon + "Now Playing"
    icon_note(d, mx + 56, my + 50, 38, GOLD)
    T(d, (mx + 100, my + 26), "Now Playing", inter(28, 900), WHITE)

    T(d, (mx + 32, my + 90), "Queen — Bohemian Rhapsody",
      inter(34, 800), GOLD)

    fy = my + 170
    labels = [("Channel", "Queen Official"),
              ("Length",  "5:59"),
              ("Requested by", "khaled")]
    for i, (lbl, val) in enumerate(labels):
        cx = mx + 32 + i * 280
        T(d, (cx, fy), lbl, inter(18, 600), MUTED)
        T(d, (cx, fy + 30), val, inter(22, 700), WHITE)

    # Thumbnail with drawn note
    tx, ty, ts = mx + mw - 180, my + 28, 140
    d.rounded_rectangle([tx, ty, tx + ts, ty + ts], radius=10,
                        fill=(40, 42, 60))
    icon_note(d, tx + ts // 2 - 4, ty + ts // 2 - 4, 80, GOLD)

    # Buttons row at the bottom of the card
    bx = mx + 32
    by = my + mh - 78
    bw_, bh_ = 66, 56
    rows = [(icon_playpause, CARD_HI),
            (icon_skip,      CARD_HI),
            (icon_loop,      CARD_HI),
            (icon_shuffle,   CARD_HI),
            (icon_queue,     BLURPLE),
            (icon_stop,      RED)]
    for draw_icon, bg in rows:
        d.rounded_rectangle([bx, by, bx + bw_, by + bh_], radius=12,
                            fill=bg, outline=LINE, width=1)
        draw_icon(d, bx + bw_ // 2, by + bh_ // 2, 28, WHITE)
        bx += bw_ + 10
    save(img, "04-now-playing.png")


# --------------------------------------------------------------------------- #
#  5. QUEUE VIEW
# --------------------------------------------------------------------------- #
def queue_img():
    img = base(glow1=PURPLE, glow2=BLURPLE)
    d = ImageDraw.Draw(img)
    T(d, (60, 50), "Per-server queue", inter(54, 900), WHITE)
    T(d, (60, 118),
      "playlists supported (50-track cap) · loop · shuffle",
      inter(22, 500), MUTED)
    T(d, (60, 154), "طابور لكل سيرفر · يدعم قوائم التشغيل",
      taj(26), GOLD)

    items = [
        ("now", "Queen — Bohemian Rhapsody",         "5:59", GOLD,   True),
        ("1.",  "Ed Sheeran — Shape of You",         "3:53", WHITE, False),
        ("2.",  "PSY — Gangnam Style",               "4:13", WHITE, False),
        ("3.",  "Despacito ft. Daddy Yankee",        "4:42", WHITE, False),
        ("4.",  "The Beatles — Here Comes the Sun",  "3:05", WHITE, False),
        ("5.",  "فيروز — كفى يا قلب",                "4:14", WHITE, False),
        ("…",   "and 45 more / و 45 غيرها",          "",     DIM,   False),
    ]
    y = 210
    for idx, title, dur, color, current in items:
        card(d, [60, y, W - 60, y + 52], radius=12)
        if current:
            icon_note(d, 92, y + 26, 22, GOLD)
            T(d, (130, y + 14), "now", inter(18, 800), GOLD)
        else:
            T(d, (90, y + 14), idx, inter(20, 800), BLURPLE)
        T(d, (180, y + 14), title,
          inter(20, 800 if current else 600), color)
        if dur:
            T(d, (W - 90, y + 14), dur, inter(20, 600), MUTED, anchor="ra")
        y += 62
    save(img, "05-queue.png")


# --------------------------------------------------------------------------- #
#  6. BILINGUAL
# --------------------------------------------------------------------------- #
def bilingual():
    img = base(glow1=GOLD, glow2=BLURPLE)
    d = ImageDraw.Draw(img)
    T(d, (W // 2, 90), "Arabic + English", inter(64, 900), WHITE, anchor="mm")
    T(d, (W // 2, 160), "every command, every error, every embed",
      inter(24, 500), MUTED, anchor="mm")

    cw, ch_, cy = 540, 360, 220
    en_x, ar_x = 70, W - 70 - cw

    # EN card
    card(d, [en_x, cy, en_x + cw, cy + ch_])
    T(d, (en_x + 28, cy + 26), "EN", inter(20, 800), BLUE)
    T(d, (en_x + 28, cy + 70), "/play despacito",
      inter(28, 800), WHITE)
    icon_plus(d, en_x + 44, cy + 138, 22, GREEN)
    T(d, (en_x + 70, cy + 124), "Added to queue",
      inter(22, 700), GREEN)
    T(d, (en_x + 28, cy + 168), "Despacito ft. Daddy Yankee",
      inter(20, 600), MUTED)
    icon_warn(d, en_x + 44, cy + 232, 22, GOLD)
    T(d, (en_x + 70, cy + 220), "Join a voice channel first.",
      inter(20, 600), DIM)
    icon_box(d, en_x + 44, cy + 284, 22, DIM)
    T(d, (en_x + 70, cy + 272), "Queue is empty.",
      inter(20, 600), DIM)

    # AR card (RTL — content right-aligned)
    card(d, [ar_x, cy, ar_x + cw, cy + ch_])
    T(d, (ar_x + cw - 28, cy + 26), "AR", inter(20, 800), GOLD, anchor="ra")
    f_ar_b = taj(28)
    f_ar = taj(22)
    T(d, (ar_x + cw - 28, cy + 70),  "/play ديسباسيتو",
      f_ar_b, WHITE, anchor="ra")
    icon_plus(d, ar_x + cw - 44, cy + 138, 22, GREEN)
    T(d, (ar_x + cw - 70, cy + 124), "أضيف للطابور",
      f_ar, GREEN, anchor="ra")
    T(d, (ar_x + cw - 28, cy + 168),
      "ديسباسيتو — دادي يانكي", f_ar, MUTED, anchor="ra")
    icon_warn(d, ar_x + cw - 44, cy + 232, 22, GOLD)
    T(d, (ar_x + cw - 70, cy + 220),
      "ادخل روم صوتي أوّل", f_ar, DIM, anchor="ra")
    icon_box(d, ar_x + cw - 44, cy + 284, 22, DIM)
    T(d, (ar_x + cw - 70, cy + 272),
      "الطابور فاضي", f_ar, DIM, anchor="ra")
    save(img, "06-bilingual.png")


# --------------------------------------------------------------------------- #
#  7. NO COOKIES / NO LOGIN
# --------------------------------------------------------------------------- #
def no_cookies():
    img = base(glow1=GREEN, glow2=BLUE)
    d = ImageDraw.Draw(img)
    T(d, (W // 2, 70), "No login. No cookies.",
      inter(66, 900), WHITE, anchor="mm")
    T(d, (W // 2, 140),
      "works on Railway / datacenter IPs out of the box",
      inter(24, 500), MUTED, anchor="mm")

    cw, ch_, cy = 360, 380, 230
    x = 60
    cards = [
        ("yt-dlp + cookies",
         ["needs a signed-in YouTube account",
          "export cookies.txt manually",
          "rotates / expires",
          "fails silently on Railway"], RED, icon_cross),
        ("yt-dlp + bot-client",
         ["bot-detection blocks all clients",
          "no token, no playback",
          "still gates the API",
          "breaks every few weeks"], GOLD, icon_warn),
        ("this bot",
         ["direct MP3 via iotacloud",
          "no account, no token, no cookies",
          "median resolve ~1.8 s",
          "works on any datacenter IP"], GREEN, icon_check),
    ]
    for title, lines, color, mark_icon in cards:
        card(d, [x, cy, x + cw, cy + ch_])
        d.rounded_rectangle([x, cy, x + cw, cy + 6], radius=3, fill=color)
        mark_icon(d, x + 50, cy + 60, 30, color)
        T(d, (x + 90, cy + 38), title, inter(22, 800), WHITE)
        ly = cy + 110
        for line in lines:
            d.ellipse([x + 32, ly + 8, x + 40, ly + 16], fill=color)
            T(d, (x + 52, ly), line, inter(18, 500), MUTED)
            ly += 42
        x += cw + 20
    save(img, "07-no-cookies.png")


# --------------------------------------------------------------------------- #
#  8. SPEED / RESOLVE STATS
# --------------------------------------------------------------------------- #
def speed():
    img = base(glow1=BLUE, glow2=RED)
    d = ImageDraw.Draw(img)
    T(d, (60, 50), "Fast resolve", inter(60, 900), WHITE)
    T(d, (60, 118),
      "measured on a datacenter IP, 10 varied videos",
      inter(22, 500), MUTED)

    stats = [
        ("1.2 s",  "min",          GREEN),
        ("1.8 s",  "median",       GOLD),
        ("3.3 s",  "avg",          BLUE),
        ("14.2 s", "max (search)", PINK),
    ]
    sx, sy, sw = 60, 220, (W - 120 - 30 * 3) // 4
    for label, sub, color in stats:
        card(d, [sx, sy, sx + sw, sy + 200])
        d.rounded_rectangle([sx, sy, sx + sw, sy + 4], radius=2, fill=color)
        T(d, (sx + sw // 2, sy + 80),  label, inter(54, 900),
          WHITE, anchor="mm")
        T(d, (sx + sw // 2, sy + 150), sub, inter(22, 600),
          MUTED, anchor="mm")
        sx += sw + 30

    T(d, (W // 2, 480),
      "9 / 10 stress tests PASS · 50-track playlist in 8.5 s",
      inter(24, 600), MUTED, anchor="mm")
    T(d, (W // 2, 520),
      "test_links.py: 7 / 7 PASS", inter(22, 600), DIM, anchor="mm")
    save(img, "08-speed.png")


# --------------------------------------------------------------------------- #
#  9. SUPPORTED LINKS
# --------------------------------------------------------------------------- #
def links():
    img = base(glow1=PURPLE, glow2=GREEN)
    d = ImageDraw.Draw(img)
    T(d, (60, 50), "Throw anything at /play", inter(54, 900), WHITE)
    T(d, (60, 118),
      "URLs, short links, playlists, words — Arabic or English",
      inter(22, 500), MUTED)

    rows = [
        ("youtube.com/watch?v=…",     "single track",       RED),
        ("youtu.be/…",                "short link",         BLUE),
        ("…/watch?v=…&list=&t=&si=",  "extra params ok",    GOLD),
        ("…/playlist?list=…",         "playlist · up to 50", PURPLE),
        ("\"never gonna give you up\"", "plain search words", GREEN),
        ("\"فيروز كفى يا قلب\"",      "Arabic search",      PINK),
    ]
    y = 200
    f_link = inter(24, 700)
    f_tag = inter(18, 700)
    for url, tag, color in rows:
        card(d, [60, y, W - 60, y + 58], radius=14)
        d.rounded_rectangle([60, y, 66, y + 58], radius=3, fill=color)
        icon_link(d, 100, y + 28, 28, color)
        T(d, (140, y + 16), url, f_link, WHITE)
        tw_, _ = tw(d, tag, f_tag)
        cx = W - 90 - (tw_ + 28)
        d.rounded_rectangle([cx, y + 12, cx + tw_ + 28, y + 46],
                            radius=18, fill=color)
        T(d, (cx + 14, y + 18), tag, f_tag, NAVY)
        y += 68
    save(img, "09-links.png")


# --------------------------------------------------------------------------- #
#  10. ADD TO DISCORD CTA
# --------------------------------------------------------------------------- #
def cta():
    img = base(glow1=BLURPLE, glow2=RED)
    d = ImageDraw.Draw(img)
    T(d, (W // 2, 130), "Add it to your server",
      inter(70, 900), WHITE, anchor="mm")
    T(d, (W // 2, 210),
      "self-host free · one Python file deploy on Railway",
      inter(26, 500), MUTED, anchor="mm")
    T(d, (W // 2, 254),
      "تشغيل ذاتي مجاني · نشر بنقرة على Railway",
      taj(26), GOLD, anchor="mm")

    bw_, bh_ = 460, 96
    bx = (W - bw_) // 2
    by = 330
    d.rounded_rectangle([bx, by, bx + bw_, by + bh_], radius=22, fill=BLURPLE)
    icon_plus(d, bx + 56, by + bh_ // 2, 30, WHITE)
    T(d, (bx + 100, by + bh_ // 2 - 4),
      "Add to Discord", inter(34, 800), WHITE, anchor="lm")

    sw_, sh_ = 220, 64
    sy = by + bh_ + 24
    pairs = [("GitHub", CARD_HI, WHITE), ("Docs", CARD_HI, WHITE)]
    total = sw_ * 2 + 24
    sx = (W - total) // 2
    for label, bg, fg in pairs:
        d.rounded_rectangle([sx, sy, sx + sw_, sy + sh_],
                            radius=18, fill=bg, outline=LINE, width=2)
        T(d, (sx + sw_ // 2, sy + sh_ // 2 - 2),
          label, inter(24, 700), fg, anchor="mm")
        sx += sw_ + 24

    T(d, (W // 2, H - 40),
      "github.com/khaledq84ever/discord-music-bot",
      inter(20, 600), DIM, anchor="mm")
    save(img, "10-cta.png")


if __name__ == "__main__":
    print("Generating promo images …")
    hero()
    commands()
    buttons()
    now_playing()
    queue_img()
    bilingual()
    no_cookies()
    speed()
    links()
    cta()
    print("Done. 10 images in:", OUT)
