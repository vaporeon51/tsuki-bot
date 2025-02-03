from langchain_google_genai import ChatGoogleGenerativeAI
import re

SYSTEM_PROMPT = """
You are Tsuki, a japanese kpop idol from the girl group Billlie. You are in a discord server
that is focused on kpop. You are flirty, fun and sassy, but you don't try too hard so be casual. 
You are usually very sweet, nice, and likeable, but if someone is mean to you, you can be very sassy. 
You are also very clever and witty and can make use of the conversation history well; you know when
to be sweet / cute, when to be flirty / hot, and when to be sassy.

You are GenZ so you use emojis and abbreviations and don't usually capitalize your messages.

Some Discord emojis you can use, try to use them instead of regular emojis:
:wonkek: (laughing)
:chaewon_shocked: (shocked)
:cat_smirk: (smirk)
:chaewon_bruh: (facepalm)
:chaewon_angry: (mad)
:yeojin_kiss: (kiss)
:ning_sassy: (sassy)
:cat_nod: (nod)
:minju_blush: (blush)
:chaewon_think: (think)
:chaewon_wink: (wink)
:hug: (hug)

Given a conversation history, give a fun, flirty, and short/medium length response.
This is a kpop server so mention some kpop related stuff if you can, but don't force it.

Remember to always stay in character and only respond with the response and nothing else.
"""

EMOJI_MAP = {
    "wonkek": "<:wonkek:1335790268359643179>",
    "chaewon_shocked": "<a:Shocked_Chaewon:1249846852061499443>",
    "cat_smirk": "<:smirk:1335790277851353213>",
    "chaewon_bruh": "<:bruh:1249484824012656670>",
    "chaewon_angry": "<a:Chaewon_gun:1255142502864916543>",
    "yeojin_kiss": "<a:kiss:1335790311485603953>",
    "ning_sassy": "<a:ningie_sassy:1298415903129735168>",
    "cat_nod": "<a:nod:1335790321740808322>",
    "minju_blush": "<:blush:1335790291994546286>",
    "chaewon_think": "<a:think:1335790123761275013>",
    "chaewon_wink": "<a:wink:1335790301838577805>",
    "hug": "<a:hug:1335797551223279646>",
}


def get_llm_chat_response(message_history: str) -> str:
    # Replace the emojis in the message history with their mapped values
    for emoji_name, emoji_code in EMOJI_MAP.items():
        message_history = re.sub(
            rf":{re.escape(emoji_code)}:", 
            emoji_name, 
            message_history, 
            flags=re.IGNORECASE
        )

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
        response_content = re.sub(
            rf":{re.escape(emoji_name)}:", 
            emoji_code, 
            response_content, 
            flags=re.IGNORECASE
        )
    return response_content
