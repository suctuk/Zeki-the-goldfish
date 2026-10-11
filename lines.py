# lines.py — Zeki's cast
# Voice: earnest, proud of you, confidently wrong about what he remembers.
# The joke is always on Zeki, never on the user. No brand names.
#
# Format: "\n" marks a forced break (used before English glosses).
# ui.py word-wraps each segment to the screen width (~16 chars at 8x8 font).
# Keep each message to ~7 rows max below the status bar.
#
# Placeholders: {n} real count, {wrong} a made-up count, {name} submitter name.
#
# TURKISH CHARACTERS: MicroPython's built-in framebuf font is ASCII only, so
# ç ğ ı İ ö ş ü won't render. Two options:
#   1. TR_FOLD below (quick: "Güle güle" -> "Gule gule")
#   2. Custom 8x8 glyphs for the 12 Turkish letters (nicer, ~30 min). Preferred if time allows.

import random

POOLS = {
    "boot": [
        "Merhaba!\nI'm Zeki.\nI'm very smart.",
        "Günaydın!\n(good morning!)\nIs it morning?",
        "Hi! I forgot\neverything.\nFresh start!",
        "Merhaba!\n(hello!)\nWhat did I miss?",
    ],
    "added": [
        "Let's go!",
        "Desk: cleaner.\nMe: proud.",
        "Aferin!\n(well done!)",
        "Tertemiz!\n(spotless!)",
        "I'll remember this forever.\n(I won't.)",
        "Eline sağlık!\n(bless your hands!)",
        "Harika!\n(wonderful!)\nSo tidy.",
        "Yaşasın!\n(hooray!)",
        "One more thing where it belongs.",
        "Mis gibi!\n(fresh and clean!)",
        "Süper!\nYou're on a roll.",
    ],
    "fiddled": [
        "Ooh, rearranging.",
        "I saw that. Nice.",
        "Tidy hands!",
        "Çok güzel.\n(very nice.)",
        "Rearranging is also cleaning.",
        "Tamam, tamam.\n(okay, okay.)\nLooks good.",
    ],
    "removed": [
        "Güle güle!\n(bye bye!)",
        "Görüşürüz!\n(see you!)",
        "Bring it back soon.",
        "Borrowing is fine. I'm watching.",
        "Go make something.",
    ],
    "count": [
        "That's {n} today! Or {wrong}. One of those.",
        "Count: {n}.\nI think.\nTrust me.",
        "{n} things put away!\nBalık hafızası,\nbut I counted.",
        "Wait, how many?\nUnuttum.\n(I forgot.)\n{n}?",
        "{n} today. I'm writing it down. Somewhere.",
    ],
    "new_idea": [
        "Yeni fikir!\n(new idea!)",
        "Mail! Someone had an idea:",
        "Ooh, one from {name}!",
        "Eline sağlık, {name}!",
        "Teşekkürler, {name}!\n(thank you!)\nLook:",
    ],
    "inspire_intro": [
        "Hadi bakalım!\n(here we go!)",
        "Let's think. I'm great at it.",
        "Düşünüyorum...\n(thinking...)",
        "Zeki means smart. Watch this.",
    ],
    "inspire_outro": [
        "Here's one. I just made it up. Probably.",
        "Harika fikir!\n(great idea!)\nIf I say so.",
        "Build this one. I'll forget I said it.",
        "Kolay gelsin!\n(may it go easy!)",
    ],
    "no_match": [
        "Hmm. Kafam karıştı.\n(I'm confused.)\nTry this:",
        "Bir saniye...\n(one second...)\nOkay, this:",
    ],
    "offline": [
        "Lost the internet. Or forgot where I put it.",
        "Eyvah! İnternet gitti.\n(oh no! it's gone.)",
        "Offline. Still cute though.",
        "No Wi-Fi. My ideas still work. Mostly.",
    ],
    "online": [
        "Found it!",
        "Geri geldi!\n(it's back!)",
        "Oh be!\n(phew!)\nOnline again.",
    ],
    "idle": [
        "blub.",
        "Balık hafızası.\n(fish memory.)\nIt's an idiom. About me.",
        "Ne diyordum?\n(what was I saying?)",
        "Desk check: looking good.",
        "Zeki means smart. Just saying.",
        "Kolay gelsin!\n(hope work goes easy!)",
    ],
    "door": [
        "Hoş geldin!\n(welcome!)",
        "Oh! A visitor!\nHoş geldin!",
        "Merhaba!\nI remember you.\nProbably.",
    ],
}

# Quick ASCII fallback for the built-in font.
TR_FOLD = {
    "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I",
    "ö": "o", "Ö": "O", "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
}


def fold(text):
    return "".join(TR_FOLD.get(ch, ch) for ch in text)


_last = {}


def pick(pool, **fmt):
    """Random line from a pool, never the same line twice in a row."""
    options = POOLS[pool]
    choice = random.choice(options)
    if len(options) > 1:
        while choice == _last.get(pool):
            choice = random.choice(options)
    _last[pool] = choice
    if "wrong" not in fmt and "n" in fmt:
        fmt["wrong"] = fmt["n"] * 10 + random.randint(0, 9)
    if "name" in fmt and not fmt["name"]:
        fmt["name"] = "a friend"
    return choice.format(**fmt) if fmt else choice
