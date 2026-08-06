# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal Django journaling app. A single `Entry` per calendar date holds five sections: a morning/evening check-in (mood sliders + a "1% better" goal with sub-goals), a Stoic reflection prompt, a biblical devotional prompt, a freeform journal entry, and exercise logging. There's also a lightweight `MomentCheckIn` for logging emotions/notes ad hoc throughout the day, independent of the daily entry.

## Commands

Run everything through the venv interpreter (no global Django install):

```
venv/Scripts/python.exe manage.py runserver
venv/Scripts/python.exe manage.py test
venv/Scripts/python.exe manage.py test entries.tests.SomeTestCase.test_name  # single test
venv/Scripts/python.exe manage.py makemigrations entries
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py check
venv/Scripts/python.exe manage.py seed_stoic_prompts       # idempotent load from entries/data/stoic_prompts.json
venv/Scripts/python.exe manage.py seed_devotional_prompts  # idempotent load from entries/data/devotional_prompts.json
```

There is no `requirements.txt` — the venv already has Django, asgiref, sqlparse, tzdata installed. If dependencies need to change, update the venv directly (`venv/Scripts/pip.exe install ...`) since there's currently no manifest to keep in sync.

`entries/bible.py` calls the real YouVersion Platform API (`api.youversion.com`), which needs a free App Key from https://platform.youversion.com. Set it as an env var before running anything that creates `DevotionalPrompt` rows: `YVP_APP_KEY=... venv/Scripts/python.exe manage.py ...`. Without it, verse-text fetches silently no-op (see below) — the app still works, prompts just show without verse text.

## Architecture

- Single app (`entries`) plus the `config` project package (settings/urls/wsgi/asgi) — no other apps.
- `config/settings.py` has a `WEATHER_*` block (lat/long/timezone) consumed by `entries/weather.py`, which does a best-effort call to the Open-Meteo API on the morning check-in page and swallows all failures (returns `None` rather than raising), since it's a fire-and-forget enrichment on a page render, not something that should ever break the check-in flow.
- Similarly, `entries/bible.py` does a best-effort call to the YouVersion Platform API to fetch `DevotionalPrompt.verse_text` for a human reference (e.g. `"Philippians 4:6-7"` → USFM `PHP.4.6-7` → live NIV text); it returns `None` on any parse/auth/network failure rather than raising. Unlike weather (fetched per-entry in a view), this is invoked at the point a `DevotionalPrompt` is created — from `DevotionalPromptAdmin.save_model` and from `seed_devotional_prompts` — and cached onto the shared `DevotionalPrompt` row rather than re-fetched per `Entry`. Bible-API display requires the copyright line in `settings.BIBLE_VERSION_ATTRIBUTION` to be shown alongside any verse text (see `entry_form.html`/`entry_detail.html`); the reading-plan *day-by-day reference lists themselves* have no public API — bible.com's plan pages are client-rendered — so those are hand-curated in `entries/data/devotional_prompts.json`, same as the Stoic prompts.
- `Entry` stores separate `morning_*_score` and `evening_*_score` fields per dimension (mental/physical/emotional/spiritual); the blended `mental_score`/`physical_score`/etc. properties average whichever of the two are present. Use the blended properties for display (e.g. calendar mood coloring); use the raw morning/evening fields in the check-in forms.
- `Goal` is a per-entry to-do list (the "1% better" goals), edited via two different formsets over the same model depending on time of day: `GoalFormSet` (add/edit/delete text, used in the morning) and `GoalCompletionFormSet` (toggle `completed` only, used in the evening).
- The three check-in views (`checkin_morning_view`, `checkin_evening_view`, `checkin_moment_view`) all get-or-create today's `Entry` via `_today_entry()` and share the `_checkin_tabs.html` partial for navigation between them; `checkin_view` is just a redirect to the morning tab.
- `EntryCreateView._next_stoic_prompt()` cycles through active `StoicPrompt` rows without repeats — it excludes prompts already used by any existing `Entry`, and only resets to the full pool once every active prompt has been used at least once. `DevotionalPrompt` selection, by contrast, is plain `order_by("?")` (random, can repeat).
- `calendar_view` computes a per-day background color (`_mood_color`) from the blended mental/physical/emotional scores, interpolating a hue between red (score 1) and green (score 10).
- No frontend build step: all CSS lives inline in `entries/templates/entries/base.html`; tab switching (`.tab-section` show/hide) is done with plain CSS classes, no JS framework.
- SQLite (`db.sqlite3`) with default Django settings; `DEBUG = True` and an insecure `SECRET_KEY` are checked in as-is — this is a single-user local app, not deployed.
- The whole app requires login (`LoginRequiredMiddleware` in `config/settings.py`), backed by the one existing Django `User` (created via `createsuperuser`, no signup flow). `/` (`entries:home`) redirects straight into the morning check-in tab. `entries/templates/entries/login.html` is a standalone page (doesn't extend `base.html`, since there's no nav to show pre-auth).
- `/all/` (`entries:list`, nav label "Journals") is a hub of four tiles — Stoic/Devotional/Freeform/Exercise — driven by the `JOURNAL_TYPES` dict in `entries/views.py`. Each tile links to `/all/<journal_type>/` (`entries:journal-type`, `JournalTypeListView`), a paginated list filtered to entries with non-blank content in that one section; `journal_type_list.html` branches on `journal_type` to pick which field to preview per row rather than using a generic field-lookup filter.
