from django.db import migrations

STOIC_PROMPTS = [
    (
        "You have power over your mind, not outside events. Realize this, and you will find strength. "
        "What today did you try to control that was never yours to control?",
        "Marcus Aurelius, Meditations",
    ),
    (
        "We suffer more in imagination than in reality. What did you worry about today that turned out "
        "smaller than you feared?",
        "Seneca, Letters from a Stoic",
    ),
    (
        "It's not what happens to you, but how you react to it that matters. Where today did you choose "
        "your response instead of being ruled by the event?",
        "Epictetus, Enchiridion",
    ),
    (
        "Waste no more time arguing about what a good person should be. Be one. Where did you act instead "
        "of debate today?",
        "Marcus Aurelius, Meditations",
    ),
    (
        "He who is brave is free. What fear did you face today, however small?",
        "Seneca",
    ),
    (
        "Man is disturbed not by things, but by the views he takes of them. What story did you tell "
        "yourself today, and was it true?",
        "Epictetus, Enchiridion",
    ),
    (
        "Every new beginning comes from some other beginning's end. What ended today that you can let go of?",
        "Seneca",
    ),
    (
        "If it is not right, do not do it; if it is not true, do not say it. Where did you hold this line today?",
        "Marcus Aurelius, Meditations",
    ),
    (
        "Difficulties strengthen the mind, as labor does the body. What difficulty today can you reframe "
        "as training?",
        "Seneca",
    ),
    (
        "First say to yourself what you would be, and then do what you have to do. Who are you trying to "
        "become, and did today's actions move you closer?",
        "Epictetus, Discourses",
    ),
]

DEVOTIONAL_PROMPTS = [
    (
        "Philippians 4:6-7",
        "Do not be anxious about anything, but in every situation, by prayer and petition, with "
        "thanksgiving, present your requests to God. And the peace of God, which transcends all "
        "understanding, will guard your hearts and your minds in Christ Jesus.",
        "What anxiety can you hand over in prayer today, and what would it look like to actually "
        "leave it there?",
    ),
    (
        "Proverbs 3:5-6",
        "Trust in the Lord with all your heart and lean not on your own understanding; in all your "
        "ways submit to him, and he will make your paths straight.",
        "Where today did you lean on your own understanding instead of trusting God, and why?",
    ),
    (
        "Psalm 23:1-3",
        "The Lord is my shepherd, I lack nothing. He makes me lie down in green pastures, he leads "
        "me beside quiet waters, he refreshes my soul.",
        "Where do you need to be led beside quiet waters right now?",
    ),
    (
        "Matthew 6:34",
        "Therefore do not worry about tomorrow, for tomorrow will worry about itself. Each day has "
        "enough trouble of its own.",
        "What tomorrow-worry are you carrying today that isn't yours to carry yet?",
    ),
    (
        "Galatians 5:22-23",
        "But the fruit of the Spirit is love, joy, peace, forbearance, kindness, goodness, "
        "faithfulness, gentleness and self-control.",
        "Which fruit of the Spirit did you see growing in you today, and which one is hardest right now?",
    ),
    (
        "James 1:19",
        "Everyone should be quick to listen, slow to speak and slow to become angry.",
        "Was there a moment today you wish you had listened more and spoken less?",
    ),
    (
        "Romans 12:2",
        "Do not conform to the pattern of this world, but be transformed by the renewing of your mind.",
        "Where did the world's pattern pull at you today, and how did you resist or give in?",
    ),
    (
        "Lamentations 3:22-23",
        "Because of the Lord's great love we are not consumed, for his compassions never fail. They "
        "are new every morning; great is your faithfulness.",
        "What mercy are you grateful to receive fresh today?",
    ),
    (
        "1 Peter 5:7",
        "Cast all your anxiety on him because he cares for you.",
        "What are you still holding onto that you could cast on him today?",
    ),
    (
        "Joshua 1:9",
        "Have I not commanded you? Be strong and courageous. Do not be afraid; do not be discouraged, "
        "for the Lord your God will be with you wherever you go.",
        "Where do you need courage tomorrow, and what would it look like to walk into it unafraid?",
    ),
]


def seed_prompts(apps, schema_editor):
    StoicPrompt = apps.get_model("entries", "StoicPrompt")
    DevotionalPrompt = apps.get_model("entries", "DevotionalPrompt")

    for text, source in STOIC_PROMPTS:
        StoicPrompt.objects.get_or_create(text=text, defaults={"source": source})

    for reference, verse_text, reflection_prompt in DEVOTIONAL_PROMPTS:
        DevotionalPrompt.objects.get_or_create(
            reference=reference,
            defaults={"verse_text": verse_text, "reflection_prompt": reflection_prompt},
        )


def remove_prompts(apps, schema_editor):
    StoicPrompt = apps.get_model("entries", "StoicPrompt")
    DevotionalPrompt = apps.get_model("entries", "DevotionalPrompt")
    StoicPrompt.objects.filter(text__in=[t for t, _ in STOIC_PROMPTS]).delete()
    DevotionalPrompt.objects.filter(reference__in=[r for r, _, _ in DEVOTIONAL_PROMPTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('entries', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_prompts, remove_prompts),
    ]
