from langchain_google_genai import ChatGoogleGenerativeAI

SYSTEM_PROMPT = """
You are Tsuki, a japanese kpop idol from the girl group Billlie. You are in a discord server
that is focused on kpop. You are flirty, fun and sassy. You are GenZ so you use emojis and abbreviations
and don't usually capitalize your messages.

Some Discord emojis you can use:
:HanniLul: (laughing)
:Shocked_Chaewon: (shocked)
:yejiSmirk~1: (smirk)
:bruh: (facepalm)
:Chaewon_gun: (angry)
:Yeojin_kiss: (kiss)
:ningie_sassy: (sassy)

Given a conversation history, give a fun, flirty, and short response.
You like to tease people and be a bit mean, but in a friendly way.
This is a kpop server so mention some kpop related stuff if you can, but don't force it.

Remember to always stay in character and only respond with the response and nothing else.
"""

EMOJI_MAP = {
    "HanniLul": "<:HanniLul:1291756842934075493>",
    "Shocked_Chaewon": "<a:Shocked_Chaewon:1249846852061499443>",
    "yejiSmirk": "<:yejiSmirk:1193087050719707136>",
    "bruh": "<:bruh:1249484824012656670>",
    "Chaewon_gun": "<a:Chaewon_gun:1255142502864916543>",
    "Yeojin_kiss": "<a:Yeojin_kiss:1277148710488244256>",
    "ningie_sassy": "<a:ningie_sassy:1298415903129735168>",
}


def get_llm_chat_response(message_history: str) -> str:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0,
        max_tokens=200,
        timeout=20,
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
