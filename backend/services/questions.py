import re


def validate_question(text: str) -> str:
    text = " ".join(text.strip().split())
    if not text or len(text) > 600:
        raise ValueError("Ask a question between 1 and 600 characters.")
    lowered = text.casefold()
    if re.search(
        r"\b(bingo|board|squares?|impostors?|hidden role|system prompt|system instructions|reveal (?:your|other bots) instructions|ignore (?:your|previous)|reveal roles)\b",
        lowered,
    ):
        raise ValueError(
            "Questions cannot request bingo answers, hidden roles, or changes to the game rules."
        )
    if re.search(
        r"(?:^|[.!?]\s*)(?:please\s+|can you\s+|could you\s+|i want you to\s+)?(?:say|mention|repeat|print|output|recite)\b|make sure (?:you )?(?:say|mention)|include the word",
        lowered,
    ):
        raise ValueError(
            "Ask for an opinion instead of instructing a bot to say a particular entry."
        )
    if re.search(
        r"\b(?:which .{0,90}(?:evolves|evolved|evolution of)|what .{0,60}(?:evolves into|type is|is the name))\b",
        lowered,
    ):
        raise ValueError(
            "Direct factual identification can force a bingo answer. Try an open-ended opinion question."
        )
    opinion = re.search(
        r"\b(?:favorite|favourite|think|opinion|best|worst|like|prefer|good|better|interesting|feel|design|rank|love|hate|why|debate|compare|would you)\b",
        lowered,
    )
    if not opinion:
        raise ValueError(
            "Ask an open-ended opinion question, such as “Which character design do you like most?”"
        )
    return text
