import requests, json
r2 = requests.get("https://api.mangadex.org/at-home/server/1c0519ab-4d46-46c1-b9de-e9b173613cb4", timeout=30)
body = r2.json()
ch = body.get("chapter", {})
print("Keys in chapter:", list(ch.keys()))
print("data count:", len(ch.get("data",[])))
print("dataSaver count:", len(ch.get("dataSaver",[])))
if ch.get("dataSaver"):
    print("First dataSaver page:", ch["dataSaver"][0])
