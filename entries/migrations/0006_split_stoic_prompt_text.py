import re

from django.db import migrations

# Existing StoicPrompt.text rows bundle a quote and a trailing reflection
# question in one string, e.g. "You have power over your mind ... What today
# did you try to control...?" This splits them into `text` (quote only) and
# `reflection_prompt` (the question), and backfills `context_summary` from
# the `source` attribution. One row (an "evening review" prompt) has no
# question mark and is handled as a special case.

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])['\"]?\s+")

SPECIAL_CASE_TEXT = (
    "The evening review: before sleep, ask what you did well, what you did "
    "badly, and what you left undone. Answer honestly for today."
)
SPECIAL_CASE_QUOTE = (
    "The evening review: before sleep, ask what you did well, what you did "
    "badly, and what you left undone."
)
SPECIAL_CASE_QUESTION = "What did you do well today, what did you do badly, and what did you leave undone?"

# Ordered (most specific first) substring -> context blurb. The prompt
# library only records a work/author attribution, not a specific chapter or
# scene, so context is given at that level rather than invented per-quote.
SOURCE_CONTEXT_RULES = [
    ("Marcus Aurelius", (
        "From Marcus Aurelius's private journal Meditations, written as personal "
        "reminders to himself during his years as Roman emperor, not intended for "
        "publication."
    )),
    ("Seneca, Letters from a Stoic", (
        "From Seneca's Letters from a Stoic (Epistulae Morales), a series of moral "
        "letters written in his later years to his friend Lucilius."
    )),
    ("Seneca, On Providence", (
        "From Seneca's essay On Providence, arguing that hardship befalling good "
        "people is not evidence against a providential order."
    )),
    ("Seneca, On the Shortness of Life", (
        "From Seneca's essay On the Shortness of Life, arguing that life is long "
        "enough if well used, and that most of it is simply wasted."
    )),
    ("Seneca, On Anger", (
        "From Seneca's essay On Anger, written to his brother Novatus, analyzing "
        "anger as a temporary madness and arguing for its restraint."
    )),
    ("Seneca", (
        "Attributed to the Roman Stoic philosopher and statesman Seneca, tutor and "
        "advisor to the emperor Nero."
    )),
    ("Epictetus, Discourses", (
        "From the Discourses of Epictetus, lectures recorded by his student Arrian; "
        "Epictetus himself was born a slave and became an influential Stoic teacher."
    )),
    ("Epictetus, Enchiridion", (
        "From the Enchiridion (Handbook), a short manual of Epictetus's teaching "
        "compiled by his student Arrian as a practical summary of the Discourses."
    )),
    ("Epictetus", (
        "Attributed to Epictetus, the former slave turned influential Stoic teacher "
        "whose lectures were recorded by his student Arrian."
    )),
    ("Musonius Rufus", (
        "From the lectures of Musonius Rufus, a 1st-century Roman Stoic teacher "
        "whose students included Epictetus."
    )),
    ("Zeno of Citium", (
        "Attributed to Zeno of Citium, the founder of Stoicism, who began teaching "
        "in Athens around 300 BC."
    )),
    ("Chrysippus", (
        "Attributed to Chrysippus, the third head of the Stoic school, whose "
        "extensive writings systematized Stoic logic and ethics (mostly lost, known "
        "through later summaries)."
    )),
    ("Cato the Younger", (
        "Attributed to Cato the Younger, a Roman statesman famous for embodying "
        "Stoic principles in his political life and death."
    )),
    ("Cato the Elder", (
        "Attributed to Cato the Elder, an early Roman statesman known for his "
        "austere discipline, later admired by the Stoics."
    )),
    ("Cleanthes", (
        "Attributed to Cleanthes, the second head of the Stoic school after Zeno, "
        "known for his Hymn to Zeus."
    )),
    ("Cicero", (
        "From the writings of Cicero, a Roman statesman and philosopher who was not "
        "himself a Stoic but who documented and engaged closely with Stoic ideas."
    )),
    ("Diogenes Laertius", (
        "From Diogenes Laertius's Lives of Eminent Philosophers, a later ancient "
        "biographical source for the sayings and lives of the Stoics."
    )),
    ("Pythagoras", (
        "Attributed to Pythagoras, whose teaching on daily self-examination was "
        "later adopted into Stoic practice."
    )),
    ("Stoic practice", (
        "A traditional Stoic exercise rather than a direct quotation — a practice "
        "used to train the mind along Stoic lines."
    )),
    ("Stoic doctrine", (
        "A summary of Stoic doctrine rather than a direct quotation from a single "
        "surviving text."
    )),
]

DEFAULT_CONTEXT = "A saying from within the Stoic philosophical tradition."


def context_for_source(source):
    for needle, blurb in SOURCE_CONTEXT_RULES:
        if needle in source:
            return blurb
    return DEFAULT_CONTEXT


def split_prompts(apps, schema_editor):
    StoicPrompt = apps.get_model("entries", "StoicPrompt")
    for prompt in StoicPrompt.objects.all():
        if prompt.text.strip() == SPECIAL_CASE_TEXT:
            prompt.text = SPECIAL_CASE_QUOTE
            prompt.reflection_prompt = SPECIAL_CASE_QUESTION
        else:
            sentences = SENTENCE_SPLIT_RE.split(prompt.text.strip())
            if len(sentences) >= 2 and sentences[-1].strip().endswith("?"):
                prompt.text = " ".join(sentences[:-1]).strip()
                prompt.reflection_prompt = sentences[-1].strip()
            # else: leave text as-is and reflection_prompt blank (none observed in practice).
        prompt.context_summary = context_for_source(prompt.source)
        prompt.save(update_fields=["text", "reflection_prompt", "context_summary"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('entries', '0005_stoicprompt_context_summary_and_more'),
    ]

    operations = [
        migrations.RunPython(split_prompts, noop),
    ]
