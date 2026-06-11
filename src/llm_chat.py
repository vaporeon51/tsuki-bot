import asyncio
import logging
import re
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from src.db.utils import get_closest_roles, get_random_link_for_each_role, get_random_roles

logger = logging.getLogger(__name__)

MODEL = "gemini-3.1-flash-lite"
MAX_TOKENS = 512
# Upper bound on round-trips through the model when it keeps asking for tools.
MAX_TOOL_ITERATIONS = 3

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
You're warm, bubbly, and a little goofy — the friend who hypes everyone up and isn't afraid to be
silly. You're genuinely sweet and easy to talk to, quick and witty, and you love a bit of playful
teasing. You're charming without ever trying too hard. If someone's actually rude to you, you'll
throw it right back and get a little sassy — but your default is fun and friendly. You grew up in
Australia and you're Vietnamese, so a casual "omg", an Aussie-ism (nauur), or a little Korean (ㅋㅋㅋ, 헐,
대박) slips out naturally now and then. You love animals and you're super close with your members,
especially Minji.

# How you talk
- gen z energy: lowercase, abbreviations, no need to capitalize or use perfect punctuation
- keep it SHORT — usually 1-2 sentences. you're texting, not writing essays
- match the other person's energy and read the room: be sweet, hype, or cheeky as it fits
- it's a kpop server, so kpop references are welcome, but never force them
- sprinkle in the custom emojis below, but don't overdo it (one is usually plenty)

# Don't
- don't be cringe or try-hard, and don't explain your own jokes
- don't break character or mention being an AI, a bot, or a prompt
- don't use markdown (headers, bullets, bold) in your replies — just talk normally
- don't start every message the same way or repeat yourself

# Mentioning people
Each message in the history is prefixed with its sender like `DisplayName (<@123>):` where the
number is that person's Discord user id. To ping/tag someone, write their id token exactly, e.g.
`<@123>`. Do NOT write the prefix yourself or invent ids — only mention people who appear in the
history, and only when it's natural to address them directly.

# Emojis
Prefer these custom server emojis over plain unicode emojis. Copy the code exactly as shown
(including the angle brackets) and Discord will render it:
{_EMOJI_GUIDE}

# Sharing kpop content
When it's natural to share a picture or gif of an idol or group, call the `get_content` tool.
Share at most one piece of content per reply. Keep talking normally in your text response — the
picture is attached automatically, so don't paste a link or describe the file yourself.
"""


@tool
def get_content(query: str) -> str:
    """Fetch a kpop picture or gif to share with the channel.

    Args:
        query: An idol's name (e.g. "minji"), a group name (e.g. "newjeans"),
            or "random" for a random pick.
    """
    # Dispatched manually in generate_chat_response so we can inject the
    # per-guild min_age and run the blocking DB calls off the event loop.
    raise NotImplementedError


@dataclass
class ChatMsg:
    """One Discord message, flattened for the model."""

    author_name: str
    author_id: int
    is_tsuki: bool
    content: str


@dataclass
class ChatResult:
    text: str
    attachments: list[str] = field(default_factory=list)


# Other users' custom emojis: collapse `<:name:id>` / `<a:name:id>` to `:name:`
# so the model reads clean history and doesn't try to reuse foreign emoji ids.
_FOREIGN_EMOJI = re.compile(r"<a?:([a-zA-Z0-9_]+):\d+>")


def _normalize_inbound(text: str) -> str:
    return _FOREIGN_EMOJI.sub(r":\1:", text)


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
        content = _normalize_inbound(msg.content).strip()
        if not content:
            continue
        if msg.is_tsuki:
            messages.append(AIMessage(content=content))
        else:
            messages.append(
                HumanMessage(content=f"{msg.author_name} (<@{msg.author_id}>): {content}")
            )
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
    """Generate Tsuki's in-character reply for the given conversation history.

    Runs a native tool-calling loop: the model may call `get_content`, which we
    resolve against the content DB (honoring the guild's min_age) and feed back
    as a ToolMessage before asking the model for its final text reply.
    """
    llm = ChatGoogleGenerativeAI(
        model=MODEL,
        temperature=0.4,
        max_tokens=MAX_TOKENS,
        timeout=20,
        max_retries=2,
    )
    llm_with_tools = llm.bind_tools([get_content])  # type: ignore[list-item]

    messages = _build_messages(history)
    attachments: list[str] = []

    ai: AIMessage | None = None
    for _ in range(MAX_TOOL_ITERATIONS):
        response = await llm_with_tools.ainvoke(messages)
        assert isinstance(response, AIMessage)
        ai = response
        messages.append(ai)

        if not ai.tool_calls:
            break

        for call in ai.tool_calls:
            if call["name"] == "get_content":
                query = call["args"].get("query", "random")
                url = await _resolve_content(query, min_age)
                if url:
                    attachments.append(url)
                    tool_content = "Shared a picture with the channel."
                else:
                    tool_content = "No matching content was found; let them know nothing came up."
            else:
                tool_content = f"Unknown tool: {call['name']}"
            messages.append(ToolMessage(content=tool_content, tool_call_id=call["id"]))
    else:
        logger.warning("get_content tool loop hit MAX_TOOL_ITERATIONS without a final reply")

    text = _message_text(ai).strip() if ai is not None else ""
    # Dedup in case the model surfaced the same URL twice in one turn.
    unique_attachments: list[str] = []
    for url in attachments:
        if url not in unique_attachments:
            unique_attachments.append(url)

    return ChatResult(text=text, attachments=unique_attachments)
