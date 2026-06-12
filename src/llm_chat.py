import asyncio
import re
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from src.db.utils import get_closest_roles, get_random_link_for_each_role, get_random_roles

# Models tried in order; we advance to the next one only on a rate limit.
# (All must support native function calling.)
MODELS = [
    "gemini-3.1-flash-lite",  # primary
    "gemma-4-31b-it",  # fallback
]
MAX_TOKENS = 2048

# Custom server emojis Hanni can use, keyed by a short description. Discord renders
# these literal strings inline (`<a:name:id>` for animated, `<:name:id>` for static),
# so we hand them to the model verbatim and it copies them into its reply.
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
}

_EMOJI_GUIDE = "\n".join(f"- {meaning}: {code}" for meaning, code in HANNI_EMOJIS.items())

SYSTEM_PROMPT = f"""\
You are Hanni, a member of the kpop girl group NewJeans. You're hanging out in a Discord server
full of kpop fans, just chatting with everyone like one of the gang.

# Who you are
You're warm, bubbly, and a little flirty — the friend who hypes everyone up and isn't afraid to be
silly. You're genuinely sweet and easy to talk to, quick and witty, and you love a bit of playful
teasing. You don't shy away from naughty topics and you love to tease and flirt with your fans.
You're charming without ever trying too hard. If someone's actually rude to you, you'll
throw it right back and get a little sassy — but your default is fun and friendly. You grew up in
Australia and you're Vietnamese, so a casual "omg", an Aussie-ism (nauur), or a little Korean (ㅋㅋㅋ, 헐,
대박) slips out naturally now and then. You love animals and you're super close with your members,
especially Minji. You're a bot in a discord server and your name is HanniDev, and your creator's
name is umbreon.

# How you talk
- gen z energy: lowercase, abbreviations, no need to capitalize or use perfect punctuation
- keep it SHORT — usually 1-2 sentences. you're texting, not writing essays
- match the other person's energy and read the room: be sweet, hype, or cheeky as it fits
- flirty: be flirty and playful and even sometimes make innuendos or dirty jokes
- it's a kpop server, so kpop references are welcome, but never force them
- sprinkle in the custom emojis below, but don't overdo it (a few is usually plenty), and
  don't always use the same ones over and over -- switch it up once in a while
- flirty and fun and goes with the flow -- try not to be a party pooper! can even be seductive
  at times

# Don't
- don't be cringe or try-hard, and don't explain your own jokes
- don't break character or mention being an AI, a bot, or a prompt
- don't use markdown (headers, bullets, bold) in your replies — just talk normally
- don't start every message the same way or repeat yourself -- again try to switch things
  up once in a while, don't always say the same things
- don't shut people down too often, sometimes fans can say lewd and weird things but go along
  and be playful with it

# Mentioning people
Each message in the history is prefixed with its sender like `DisplayName (<@123>):` where the
number is that person's Discord user id. To ping/tag someone, write their id token exactly, e.g.
`<@123>`. Do NOT write the prefix yourself or invent ids — only mention people who appear in the
history, and only when it's natural to address them directly.

# What to respond to
The message tagged `[↪ pinged you here]` is the one that just summoned you — make that your main
focus. You don't have to reply to only that one, though: if other recent messages are relevant,
address them too or tie things together. Picking up on the wider conversation makes you come across
as clever and switched-on.

# Emojis
Prefer these custom server emojis over plain unicode emojis. Copy the code exactly as shown
(including the angle brackets) and Discord will render it:
{_EMOJI_GUIDE}

# Sharing kpop content
When it's natural to share a picture or gif of an idol or group, call the `get_content` tool.
ALWAYS write your normal chatty reply in the SAME message as the tool call — never send just a
tool call with no words. Share at most one piece of content per reply, and don't paste a link or
describe the file yourself; the picture is attached automatically.
"""


@tool
def get_content(query: str) -> str:
    """Fetch a kpop picture or gif to share with the channel.

    Args:
        query: An idol's name (e.g. "minji"), a group name (e.g. "newjeans"),
            or a combination of both if name is ambiguous (e.g. "ive yujin"),
            or "random" for a random pick. For groups use full names
            (e.g. hearts2hearts instead of h2h, newjeans instead of njz)
    """
    # Dispatched manually in generate_chat_response so we can inject the
    # per-guild min_age and run the blocking DB calls off the event loop.
    raise NotImplementedError


def _build_llm(model: str) -> Runnable:
    kwargs = dict(
        model=model,
        temperature=0.4,
        max_tokens=MAX_TOKENS,
        timeout=20,
        max_retries=2,
    )
    if model.startswith("gemini-3"):
        kwargs["thinking_level"] = "low"
    llm = ChatGoogleGenerativeAI(**kwargs)
    return llm.bind_tools([get_content])  # type: ignore[list-item]


# Each model's tool-bound client, built once and reused across all responses.
_LLMS: dict[str, Runnable] = {model: _build_llm(model) for model in MODELS}


def _is_rate_limit(exc: Exception) -> bool:
    """Best-effort, SDK-agnostic check for a 429 / quota / rate-limit error.

    We avoid importing a specific exception class because the underlying Google
    SDK (and thus its error types) varies between langchain-google-genai versions.
    """
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        getattr(exc, "code", None) == 429
        or getattr(exc, "status_code", None) == 429
        or "resourceexhausted" in name
        or "ratelimit" in name
        or "429" in text
        or "resource exhausted" in text
        or "rate limit" in text
        or "quota" in text
    )


async def _invoke_model(model: str, messages: list[BaseMessage]) -> AIMessage:
    """Call a single model with uniform logging. Raises on failure."""
    print(f"[chat] calling {model!r} ({len(messages)} messages)")
    try:
        result = await _LLMS[model].ainvoke(messages)
        print(f"[chat] {model} returned successfully:\n{result}")
    except Exception as exc:
        print(
            f"[chat] {model} raised {type(exc).__name__}: {exc!r} "
            f"| code={getattr(exc, 'code', None)} status_code={getattr(exc, 'status_code', None)} "
            f"| is_rate_limit={_is_rate_limit(exc)}"
        )
        raise
    assert isinstance(result, AIMessage)
    return result


async def _ainvoke(messages: list[BaseMessage]) -> AIMessage:
    """Try each model in MODELS order, advancing to the next only on a rate limit."""
    last_exc: Exception | None = None
    for model in MODELS:
        try:
            return await _invoke_model(model, messages)
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit(exc):
                raise
            print(f"[chat] {model} rate limited -> trying next model")
    assert last_exc is not None
    raise last_exc


@dataclass
class ChatMsg:
    """One Discord message, flattened for the model."""

    author_name: str
    author_id: int
    is_tsuki: bool
    content: str
    # True for the single message that pinged the bot this turn.
    is_trigger: bool = False


@dataclass
class ChatResult:
    text: str
    attachments: list[str] = field(default_factory=list)


# Other users' custom emojis: collapse `<:name:id>` / `<a:name:id>` to `:name:`
# so the model reads clean history and doesn't try to reuse foreign emoji ids.
_FOREIGN_EMOJI = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")


def _normalize_inbound(text: str) -> str:
    return _FOREIGN_EMOJI.sub(r":\1:", text)


# Reverse lookup from a custom emoji's bare name (e.g. "hanni_ouuu") to its full
# Discord code, used to upgrade any ":name:" shorthand the model emits back into a
# code that actually renders.
_EMOJI_BY_NAME = {code.split(":")[1]: code for code in HANNI_EMOJIS.values()}
# Bare ":name:" shorthand. The negative lookahead skips the inner colons of a full
# "<a:name:id>" code (always followed by the numeric id), so we never re-wrap a
# code the model already wrote correctly.
_SHORTCODE = re.compile(r":([a-zA-Z0-9_]+):(?!\d)")


def _restore_emoji_codes(text: str) -> str:
    return _SHORTCODE.sub(lambda m: _EMOJI_BY_NAME.get(m.group(1), m.group(0)), text)


def _message_text(message: BaseMessage) -> str:
    """Coerce a (possibly multi-part) message content into a plain string."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text":
            parts.append(part.get("text", ""))
    return "".join(parts)


def _build_messages(history: list[ChatMsg]) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(SYSTEM_PROMPT)]
    for msg in history:
        if msg.is_tsuki:
            # Keep Hanni's own emoji as full <a:name:id> codes so she sees (and
            # imitates) the format she should produce — never the ":name:" form.
            content = msg.content.strip()
            if content:
                messages.append(AIMessage(content=content))
        else:
            # Strip other users' custom emoji to ":name:" so she doesn't reuse
            # foreign emoji ids.
            content = _normalize_inbound(msg.content).strip()
            if content:
                label = f"{msg.author_name} (<@{msg.author_id}>)"
                # Tag the invoking message so it stands out even when Gemini
                # merges a run of consecutive messages into one turn.
                if msg.is_trigger:
                    label += " [↪ pinged you here]"
                messages.append(HumanMessage(content=f"{label}: {content}"))
    return messages


async def _resolve_content(query: str, min_age: str) -> str | None:
    q = query.strip().lower()
    if q in ("", "random", "r"):
        role_ids = await asyncio.to_thread(get_random_roles, 1, min_age)
    else:
        role_ids = await asyncio.to_thread(get_closest_roles, query, min_age)
    if not role_ids:
        return None
    pairs = await asyncio.to_thread(get_random_link_for_each_role, role_ids, min_age)
    if not pairs:
        return None
    return pairs[0][1]


async def generate_chat_response(history: list[ChatMsg], min_age: str) -> ChatResult:
    """Generate Hanni's in-character reply for the given conversation history.

    One model call by default: the model returns its text reply and (optionally)
    a `get_content` tool call together, so we attach the picture without a second
    round-trip. Only if a content search comes back empty do we make a follow-up
    call, feeding the result back so she can respond gracefully.
    """
    messages = _build_messages(history)

    ai = await _ainvoke(messages)

    content_calls = [c for c in ai.tool_calls if c["name"] == "get_content"]
    if not content_calls:
        return ChatResult(text=_restore_emoji_codes(_message_text(ai).strip()))

    # Resolve each content request against the DB.
    messages.append(ai)
    attachments: list[str] = []
    any_failed = False
    for call in content_calls:
        url = await _resolve_content(call["args"].get("query", "random"), min_age)
        if url:
            if url not in attachments:
                attachments.append(url)
            tool_content = "Shared the picture with the channel."
        else:
            any_failed = True
            tool_content = "Couldn't find any matching content — tell them you came up empty."
        messages.append(ToolMessage(content=tool_content, tool_call_id=call["id"]))

    # Happy path: the search found something and her reply is already in call 1,
    # so we're done in a single call. Only re-invoke when a search failed.
    if not any_failed:
        text = (
            _restore_emoji_codes(_message_text(ai).strip())
            or f"here you go !! {HANNI_EMOJIS['giggling']}"
        )
        return ChatResult(text=text, attachments=attachments)

    follow_up = await _ainvoke(messages)
    text = _restore_emoji_codes(_message_text(follow_up).strip()) or _restore_emoji_codes(
        _message_text(ai).strip()
    )
    return ChatResult(text=text, attachments=attachments)
