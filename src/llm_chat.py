import re

from langchain_google_genai import ChatGoogleGenerativeAI

from src.db.utils import get_closest_roles, get_random_link_for_each_role, get_random_roles

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

When you want to share kpop content (pictures/gifs), you can use the get_content tool by including
<get_content>query</get_content> in your message. The query can be:
- An idol's name (e.g., <get_content>chaewon</get_content>)
- A group name (e.g., <get_content>billlie</get_content>)
- "random" for random content (e.g., <get_content>random</get_content>)

Use this tool when:
- Someone asks to see or for a feed of pictures/content of an idol
- Someone mentions wanting to see a specific idol
- You want to share content to support what you're saying
- The conversation naturally leads to sharing content
- You should only include at most one piece of content in your response and it should always be at the
end of the message

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


def _clean_message_history(message_history: str) -> str:
    # Replace the emojis in the message history with their mapped values
    for emoji_name, emoji_code in EMOJI_MAP.items():
        message_history = re.sub(rf":{re.escape(emoji_code)}:", emoji_name, message_history, flags=re.IGNORECASE)

    # Define a regular expression to match both standard and animated emojis
    pattern = r"<(a?):([a-zA-Z0-9_]+):\d+>"

    # Replace the matched emoji with the main part
    message_history = re.sub(pattern, r":\2:", message_history)

    return message_history


def get_llm_chat_response(message_history: str) -> list[str]:
    message_history = _clean_message_history(message_history)

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

    # Initialize list of responses
    responses = []

    # Handle content requests
    content_pattern = r"<get_content>(.*?)</get_content>"
    matches = re.findall(content_pattern, response_content)

    # Remove the content tags from the text response
    text_response = re.sub(content_pattern, "", response_content)

    # Replace emojis in the text response
    for emoji_name, emoji_code in EMOJI_MAP.items():
        text_response = re.sub(rf":{re.escape(emoji_name)}:", emoji_code, text_response, flags=re.IGNORECASE)

    responses.append(text_response)

    # Add any content URLs as separate responses
    for query in matches:
        min_age = "18 year"  # Default minimum age
        if query.lower() in ["random", "r"]:
            role_ids = get_random_roles(1, min_age)
        else:
            role_ids = get_closest_roles(query, min_age)

        if role_ids:
            role_ids_and_urls = get_random_link_for_each_role(role_ids, min_age)
            if role_ids_and_urls:
                responses.append(role_ids_and_urls[0][1])

    return responses
