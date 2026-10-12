# inspire.py — "inspire me": 4 multiple-choice questions -> a matched idea.
#
# Controls: turn = cycle options, click = confirm, long press = back
# (on the first question: cancel). On the idea: turn = another idea,
# click = done. 30 s without input -> back to IDLE.
#
# Matcher (spec): score = 2 x time match + 1 per `does` match + 1 per `vibe`
# match; "My desk only" keeps ideas whose parts are all in config.INVENTORY.
# Random order within a score, so repeat runs vary. Nothing scores -> a
# random-word mashup, so Zeki always answers.

import json
import random
import time

import config as C
import lines
import ui

INTRO, ASK, THINK, IDEA, OUTRO = "intro", "ask", "think", "idea", "outro"


def load_ideas(path=C.IDEAS_FILE):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print("inspire: can't load", path, e)
        return []


def score(idea, a):
    s = 2 if idea.get("time") == a.get("time") else 0
    if a.get("does") in idea.get("does", ()):
        s += 1
    if a.get("vibe") in idea.get("vibe", ()):
        s += 1
    return s


def rank(ideas, a):
    """Ideas with score > 0, best first, shuffled within each score."""
    if a.get("parts") == "desk":
        ideas = [i for i in ideas if all(p in C.INVENTORY for p in i.get("parts", ()))]
    scored = [(score(i, a), random.getrandbits(16), i) for i in ideas]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [i for s, _, i in scored if s > 0]


_THING = ("gadget", "contraption", "widget", "doohickey")
_DOES = {"sense": "senses things", "show": "lights up", "move": "wiggles",
         "noise": "makes noise", "online": "talks to the internet"}
_PART = ("a load cell", "a servo", "an LED stick", "a soil sensor",
         "a heating pad", "a distance sensor", "a buzzer")


def mashup(a):
    vibe = a.get("vibe") or "silly"
    thing = "desk toy" if vibe == "desk" else random.choice(_THING)
    adj = "silly" if vibe == "desk" else vibe
    verb = _DOES.get(a.get("does"), "does something")
    return {"id": "mashup", "title": "Zeki Original",
            "text": "A {} {} that {} using {}.".format(adj, thing, verb, random.choice(_PART))}


def _arrows(label):
    s = "< {} >".format(label)
    return s if len(s) <= 16 else "<{}>".format(label)


class Inspire:
    """Drive with tick(now, events); returns False when the flow is over."""

    def __init__(self, screen, chime=None):
        self.screen = screen
        self.chime = chime
        self.ideas = load_ideas()
        self.sel = [0] * len(C.QUESTIONS)
        self.answers = {}
        self.q = 0
        self.picks = []
        self.pick_i = 0
        self.color = C.COLOR_INSPIRE
        now = time.ticks_ms()
        self.last_input = now
        self._go(INTRO, now)
        self.screen.say(lines.pick("inspire_intro"))

    def _go(self, step, now):
        self.step = step
        self.step_t = now

    def _beep(self, notes):
        if self.chime:
            self.chime.play(notes)

    # --- screens -----------------------------------------------------------
    def _ask(self):
        key, question, opts = C.QUESTIONS[self.q]
        i = self.sel[self.q]
        rows = ui.wrap(question)[:2] + [""]
        hi = len(rows)
        rows += [_arrows(opts[i][1]), "", "{}/{}".format(i + 1, len(opts))]
        self.screen.show(rows, hi=hi)
        self.color = C.OPTION_COLORS[i % len(C.OPTION_COLORS)]

    def _show_idea(self):
        idea = self.picks[self.pick_i]
        self.screen.show([idea["title"]] + ui.wrap(idea["text"])[:5], hi=0)
        self.color = C.COLOR_INSPIRE
        print("inspire: {} -> {} (score {})".format(
            self.answers, idea["id"], score(idea, self.answers)))

    def _finish_questions(self, now):
        self.picks = rank(self.ideas, self.answers)
        self.pick_i = 0
        if self.picks:
            self._go(IDEA, now)
            self._show_idea()
            self._beep(C.CHIME_IDEA)
        else:
            self.picks = [mashup(self.answers)]
            self._go(THINK, now)
            self.screen.say(lines.pick("no_match"))

    # --- loop ----------------------------------------------------------------
    def tick(self, now, events):
        if events:
            self.last_input = now
        elif time.ticks_diff(now, self.last_input) > C.INSPIRE_TIMEOUT_MS:
            print("inspire: timed out")
            return False

        for ev in events:
            kind = ev[0]
            if self.step == INTRO:
                if kind == "click":
                    self._start_questions(now)
                elif kind == "long":
                    return False
            elif self.step == ASK:
                n = len(C.QUESTIONS[self.q][2])
                if kind == "turn":
                    self.sel[self.q] = (self.sel[self.q] + ev[1]) % n
                    self._ask()
                elif kind == "click":
                    key, _, opts = C.QUESTIONS[self.q]
                    self.answers[key] = opts[self.sel[self.q]][0]
                    self._beep(C.CHIME_TICK)
                    self.q += 1
                    if self.q < len(C.QUESTIONS):
                        self._ask()
                    else:
                        self._finish_questions(now)
                elif kind == "long":
                    if self.q == 0:
                        return False
                    self.q -= 1
                    self._ask()
            elif self.step in (IDEA, THINK):
                if kind == "turn" and len(self.picks) > 1:
                    self.pick_i = (self.pick_i + (1 if ev[1] > 0 else -1)) % len(self.picks)
                    self._go(IDEA, now)
                    self._show_idea()
                elif kind == "click":
                    self._go(OUTRO, now)
                    self.screen.say(lines.pick("inspire_outro"))
                elif kind == "long":
                    self.q = len(C.QUESTIONS) - 1
                    self._go(ASK, now)
                    self._ask()
            elif self.step == OUTRO:
                if kind in ("click", "long"):
                    return False

        if self.step == INTRO and time.ticks_diff(now, self.step_t) >= C.INSPIRE_INTRO_MS:
            self._start_questions(now)
        elif self.step == THINK and time.ticks_diff(now, self.step_t) >= C.INSPIRE_INTRO_MS:
            self._go(IDEA, now)
            self._show_idea()
            self._beep(C.CHIME_IDEA)
        elif self.step == OUTRO and time.ticks_diff(now, self.step_t) >= C.INSPIRE_OUTRO_MS:
            return False
        return True

    def _start_questions(self, now):
        self.q = 0
        self._go(ASK, now)
        self._ask()
