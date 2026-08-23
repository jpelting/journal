import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

LEGACY_STATE_FILE = settings.BASE_DIR / ".announcement_gen_state.json"

MODEL = "claude-haiku-4-5"
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """\
You write short "What's New" announcements for the users of a personal journaling \
web app called The Wax Tablet. Your readers are not programmers - never use \
technical terms like "refactor", "migration", "backend", "endpoint", "queryset", \
or "template". Write the way you'd explain a change to a friend over text.

You'll be given a numbered list of git commit messages. Most commits are internal \
(dependency bumps, refactors, test fixes, typo corrections, CI/deploy config) and \
should be skipped entirely - only include commits that a user would actually \
notice or care about: a new feature they can use, a bug they'd have hit, or a \
visible improvement.

For each commit worth announcing, write:
- category: "feature" for something new, "fix" for a bug fix, "improvement" for \
a tweak to something that already existed
- title: a short plain-language headline, under 12 words
- description: 1-2 short sentences explaining what changed, in plain language
- location: for features/improvements, where in the app to find it (e.g. \
"Morning Check-in"); leave blank for fixes with nothing new to go look at

Return every commit not worth announcing to a user by simply omitting it. If none \
of the commits are user-facing, return an empty list. Do not invent details that \
aren't in the commit message - if a commit message is too vague to explain \
clearly, skip it rather than guess.
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "announcements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["feature", "fix", "improvement"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["category", "title", "description", "location"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["announcements"],
    "additionalProperties": False,
}


class Command(BaseCommand):
    help = (
        "Drafts What's New announcements from recent git commits using the Claude API, "
        "saved inactive for review in /admin/entries/announcement/. Needs a git checkout "
        "with real history (run locally, or in CI - see .github/workflows/generate-announcements.yml) "
        "and a DATABASE_URL reaching production, since state (the last commit processed) "
        "is tracked in AnnouncementGenState so both places stay in sync."
    )

    def handle(self, *args, **options):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise CommandError(
                "ANTHROPIC_API_KEY is not set. Get an API key from console.anthropic.com "
                "and set it as an environment variable before running this command."
            )

        repo_root = settings.BASE_DIR
        last_sha = self._read_last_sha()
        commits = self._commits_since(repo_root, last_sha)

        if not commits:
            self.stdout.write("No new commits since the last run - nothing to draft.")
            return

        self.stdout.write(f"Drafting announcements from {len(commits)} new commit(s)...")
        drafts = self._draft_announcements(api_key, commits)

        from entries.models import Announcement

        created = 0
        for draft in drafts:
            Announcement.objects.create(
                category=draft["category"],
                title=draft["title"],
                description=draft["description"],
                location=draft.get("location", ""),
                is_active=False,
            )
            created += 1

        head_sha = self._current_head(repo_root)
        self._write_last_sha(head_sha)

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Drafted {created} announcement(s) from {len(commits)} commit(s) "
                    f"({len(commits) - created} skipped as not user-facing). "
                    "Review them at /admin/entries/announcement/ and check Is Active "
                    "to publish - they're saved inactive by default."
                )
            )
        else:
            self.stdout.write(
                f"Reviewed {len(commits)} commit(s) - none looked user-facing, nothing drafted."
            )

    def _read_last_sha(self):
        from entries.models import AnnouncementGenState

        state = AnnouncementGenState.objects.first()
        if state:
            return state.last_sha or None

        # No DB state yet - most likely the very first run against this database.
        # Fall back to the legacy local file, if one exists, so switching over doesn't
        # re-announce a batch of commits an earlier local-only run already covered.
        if not LEGACY_STATE_FILE.exists():
            return None
        try:
            return json.loads(LEGACY_STATE_FILE.read_text(encoding="utf-8")).get("last_sha")
        except (json.JSONDecodeError, OSError):
            return None

    def _write_last_sha(self, sha):
        from entries.models import AnnouncementGenState

        state, _ = AnnouncementGenState.objects.get_or_create(pk=1)
        state.last_sha = sha
        state.save(update_fields=["last_sha", "updated_at"])

    def _current_head(self, repo_root):
        return self._git(repo_root, ["rev-parse", "HEAD"]).strip()

    def _commits_since(self, repo_root, last_sha):
        commit_range = f"{last_sha}..HEAD" if last_sha else "-30"
        args = ["log", "--pretty=format:%H%x00%s%x00%b%x01"]
        args += [commit_range] if last_sha else [commit_range, "HEAD"]
        raw = self._git(repo_root, args)

        commits = []
        for entry in raw.split("\x01"):
            entry = entry.strip()
            if not entry:
                continue
            sha, subject, body = (entry.split("\x00") + ["", ""])[:3]
            commits.append({"sha": sha, "subject": subject, "body": body.strip()})
        commits.reverse()  # oldest first, matches reading order
        return commits

    def _git(self, repo_root, args):
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError:
            raise CommandError("git is not on PATH - this command must run from a git checkout.")
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"git {' '.join(args)} failed: {exc.stderr.strip()}")
        return result.stdout

    def _draft_announcements(self, api_key, commits):
        commit_list = "\n\n".join(
            f"{i}. {c['subject']}" + (f"\n{c['body']}" if c["body"] else "")
            for i, c in enumerate(commits, 1)
        )

        body = json.dumps(
            {
                "model": MODEL,
                "max_tokens": 4096,
                "system": SYSTEM_PROMPT,
                "output_config": {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                "messages": [{"role": "user", "content": commit_list}],
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            API_URL,
            data=body,
            method="POST",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CommandError(f"Claude API request failed ({exc.code}): {detail}")
        except urllib.error.URLError as exc:
            raise CommandError(f"Could not reach the Claude API: {exc.reason}")

        if payload.get("stop_reason") == "refusal":
            raise CommandError("Claude declined to draft announcements for this commit batch.")

        text = next(block["text"] for block in payload["content"] if block["type"] == "text")
        return json.loads(text)["announcements"]
