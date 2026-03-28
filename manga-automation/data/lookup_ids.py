import requests, time
titles = ["One Piece","Jujutsu Kaisen","Chainsaw Man","Spy x Family","Demon Slayer","Attack on Titan","Tokyo Revengers"]
for t in titles:
    r = requests.get("https://api.mangadex.org/manga", params={"title": t, "limit": 1, "availableTranslatedLanguage[]": ["en"]}, timeout=15)
    data = r.json().get("data", [])
    if data:
        m = data[0]
        en = m["attributes"]["title"].get("en", list(m["attributes"]["title"].values())[0])
        print(t, "->", m["id"], en)
    else:
        print(t, "-> NOT FOUND")
    time.sleep(0.6)
