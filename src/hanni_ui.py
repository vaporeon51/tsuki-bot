"""Shared public-facing Hanni styling and compact canned copy."""

HANNI_EMOJIS: dict[str, str] = {
    "sad": "<a:hanni_sad:1514631028973633546>",
    "ooooh / teasing": "<a:hanni_ouuu:1514631027601965217>",
    "hug": "<a:hanni_minji_hug:1514631025978900602>",
    "blowing a kiss": "<a:hanni_kissme:1514631023910981683>",
    "thinking": "<:hanni_think:1514630252104515585>",
    "omg / shocked": "<:hanni_omg:1514630248325447770>",
    "oh no / embarrassed": "<:hanni_notlikethis:1514630247486591016>",
    "mad": "<:hanni_mad:1514630245032919110>",
    "kiss": "<a:hanni_kiss:1514630242013155458>",
    "laughing": "<a:hanni_kek:1514630240062935171>",
    "giggling": "<a:hanni_giggle:1514630238124900464>",
    "cozy / comfy": "<:hanni_cozyblanket:1514630236522938408>",
    "awkward smile": "<a:hanni_awkwardsmile:1514630233716690974>",
    "wink": "<:cat_wink:1514630232232034344>",
    "screaming / excited": "<a:cat_screaming:1514630231129067560>",
    "pat / there there": "<a:bear_pat:1514630230445396019>",
    "scream / very excited": "<a:haerin_scream:1515062708071038997>",
    "bowing / thank you": "<a:hanni_bow:1515062709685584062>",
    "cursed / derp": "<a:hanni_cursed:1515062711309045871>",
    "excited / jumping": "<a:hanni_excited:1515062712919396402>",
    "hello / wave": "<a:hanni_hello:1515062715415134389>",
    "eating / nom": "<a:hannichomp:1538525142999900200>",
    "punch / boop": "<a:hanni_punch:1515062717809954898>",
    "swag / cool": "<a:hanni_swag:1515062719378620496>",
    "despair": "<:hanni_despair:1515066515408425031>",
    "no no / finger wag": "<a:hanni_no:1515066516775633066>",
    "pull hearts / flirt": "<a:hanni_pull_hearts:1515066517933527041>",
    "shake my head / no": "<a:hanni_smh:1515066520089268414>",
    "typing / chatting": "<a:hanni_typing:1515066521129320601>",
    "yikes / cringe": "<a:hanni_yikes:1515066523172077730>",
}

# Embed colors: blush for general Hanni UI, lilac for choices, gold for wins,
# mint for positive outcomes, and rose for gentle failures.
HANNI_BLUSH = 0xE8A4C9
HANNI_LILAC = 0xB8A7E8
HANNI_GOLD = 0xF4C76B
HANNI_MINT = 0x9FD8BE
HANNI_ROSE = 0xE58F9E


def feed_started_message(label: str, sort_by: str, count: int, interval: int) -> str:
    sort_label = {"random": "random", "latest": "latest", "oldest": "oldest", "top": "top-rated"}[sort_by]
    return (
        f"starting a {sort_label} feed of `{label}`! "
        f"{count} posts, one every {interval} seconds {HANNI_EMOJIS['eating / nom']}"
    )


def feed_finished_message(cancelled: bool = False) -> str:
    if cancelled:
        return f"an admin stopped the feed {HANNI_EMOJIS['oh no / embarrassed']}"
    return f"all done! hope you found a favorite {HANNI_EMOJIS['bowing / thank you']}"


def content_not_found_message(query: str) -> str:
    return f"i couldn't find any content for `{query}` rn {HANNI_EMOJIS['sad']}"


def content_unavailable_message() -> str:
    return f"i couldn't find enough content for that rn {HANNI_EMOJIS['sad']}"


def transient_error_message() -> str:
    return f"something got tangled up inside me, try again in a sec {HANNI_EMOJIS['despair']}"
