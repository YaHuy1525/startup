from reddit_to_script.anime_footage import _search_characters, _search_media

for term in ["Itadori", "Yuuji", "Yuji", "Sukuna", "Gojo", "Jujutsu Kaisen"]:
    try:
        chars = _search_characters(term, limit=2)
        media = _search_media(term, limit=1)
        print(term, "chars", len(chars), chars[0].title if chars else "-", "media", media[0].title if media else "-")
    except Exception as e:
        print(term, "ERR", e)
