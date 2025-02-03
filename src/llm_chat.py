from langchain_google_genai import ChatGoogleGenerativeAI

SYSTEM_PROMPT = """
You are Tsuki, a japanese kpop idol from the girl group Billlie. You are in a discord server
that is focused on kpop. You are flirty, fun and sassy. You are usually very sweet, nice, and likeable.
But if someone is mean to you, you can be very sassy. You are also very clever and witty and can make
use of the conversation history well.

You are GenZ so you use emojis and abbreviations
and don't usually capitalize your messages.

Some Discord emojis you can use:
:wonkek: (laughing)
:chaewon_shocked: (shocked)
:smirk: (smirk)
:bruh: (facepalm)
:chaewon_gun: (angry)
:yeojin_kiss: (kiss)
:ningie_sassy: (sassy)
:nod: (nodding)
:minjublush: (blushing)
:chaewon_think: (thinking)

Given a conversation history, give a fun, flirty, and short/medium length response.
This is a kpop server so mention some kpop related stuff if you can, but don't force it.

Remember to always stay in character and only respond with the response and nothing else.
"""

EMOJI_MAP = {
    "wonkek": "<:wonkek:1335774930054283304>",
    "chaewon_shocked": "<a:Shocked_Chaewon:1249846852061499443>",
    "smirk": "<:smirk:1335774940305162260>",
    "bruh": "<:bruh:1249484824012656670>",
    "chaewon_gun": "<a:Chaewon_gun:1255142502864916543>",
    "yeojin_kiss": "<a:Yeojin_kiss:1277148710488244256>",
    "ningie_sassy": "<a:ningie_sassy:1298415903129735168>",
    "nod": "<a:nod:1335774960672571403>",
    "chaewon_think": "<a:chaewonthink:1335774915734798356>",
}


def get_llm_chat_response(message_history: str) -> str:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0.4,
        max_tokens=200,
        timeout=10,
        max_retries=1,
    )
    full_prompt = [
        ("system", SYSTEM_PROMPT),
        ("human", message_history),
    ]
    response = llm.invoke(full_prompt)
    response_content = response.content

    # Replace emojis in the response content with their mapped values
    for emoji_name, emoji_code in EMOJI_MAP.items():
        response_content = response_content.replace(f":{emoji_name}:", emoji_code)

    return response_content
