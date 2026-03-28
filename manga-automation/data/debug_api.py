import requests, json
# Step 1: find latest chapter
r = requests.get("https://api.mangadex.org/manga/a77742b1-befd-49a4-bff5-1ad4e6b0ef7b/feed",
    params={"limit":1,"order[chapter]":"desc","translatedLanguage[]":["en"],"contentRating[]":["safe","suggestive"]},
    timeout=30)
print("Feed status:", r.status_code)
data = r.json().get("data",[])
if not data:
    print("No chapter data!")
else:
    ch = data[0]
    ch_id = ch["id"]
    print("Chapter found:", ch_id, ch["attributes"].get("chapter"))
    # Step 2: at-home server
    r2 = requests.get(f"https://api.mangadex.org/at-home/server/{ch_id}", timeout=30)
    print("At-home status:", r2.status_code)
    body = r2.json()
    chapter_data = body.get("chapter",{})
    pages = chapter_data.get("data",[])
    print("Pages count:", len(pages))
    if pages:
        print("First page URL:", body["baseUrl"] + "/data/" + chapter_data["hash"] + "/" + pages[0])
