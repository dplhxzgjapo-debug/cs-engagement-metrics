#!/usr/bin/env python3
"""Scrape yakkun.com Pokemon Champions singles ranking and output data.json"""
import re, json, urllib.request, datetime

URL = "https://yakkun.com/ch/ranking.htm"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch():
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("euc-jp", errors="replace")

def parse_rankings(text):
    """Extract ranking list from page index menu (deduplicated)."""
    matches = re.findall(r'(\d+)\u4f4d: ([^<"]+)', text)
    seen, out = set(), []
    for rank, name in matches:
        if rank not in seen:
            seen.add(rank)
            out.append({"rank": int(rank), "name": name.strip()})
    return out

def parse_pokemon_details(text, rankings):
    """Extract stats, types, abilities, and mentioned moves per pokemon."""
    results = []
    for i, entry in enumerate(rankings):
        rank = entry["rank"]
        name = entry["name"]
        # Find the h2 section for this pokemon
        header = f'{rank}\u4f4d: {name}</h2>'
        start = text.find(header)
        if start < 0:
            results.append({**entry, "types": [], "stats": {}, "abilities": [], "moves_mentioned": []})
            continue
        # Find the end (next h2 or end of text)
        next_h2 = text.find('<h2 id="', start + len(header))
        chunk = text[start:next_h2] if next_h2 > 0 else text[start:start+8000]

        # Types
        types = re.findall(r'alt="([^"]+)"[^>]*/>\s*</li>', chunk)
        type_map = {
            "ノーマル":"normal","ほのお":"fire","みず":"water","くさ":"grass",
            "でんき":"electric","こおり":"ice","かくとう":"fighting","どく":"poison",
            "じめん":"ground","ひこう":"flying","エスパー":"psychic","むし":"bug",
            "いわ":"rock","ゴースト":"ghost","ドラゴン":"dragon","あく":"dark",
            "はがね":"steel","フェアリー":"fairy"
        }
        types_en = [type_map.get(t, t) for t in types if t in type_map]

        # Stats
        stats = {}
        stat_matches = re.findall(r'<dt>(HP|攻撃|防御|特攻|特防|素早)</dt><dd[^>]*>(\d+)</dd>', chunk)
        stat_keys = {"HP":"hp","攻撃":"atk","防御":"def","特攻":"spa","特防":"spd","素早":"spe"}
        for label, val in stat_matches:
            stats[stat_keys.get(label, label)] = int(val)

        # Abilities
        abilities = re.findall(r'class="ability">([^<]+)</a>', chunk)

        # Moves mentioned in description
        moves = re.findall(r'class="move">([^<]+)</a>', chunk)
        # Deduplicate while preserving order
        seen_moves = set()
        unique_moves = []
        for m in moves:
            if m not in seen_moves:
                seen_moves.add(m)
                unique_moves.append(m)

        results.append({
            **entry,
            "types": types_en,
            "stats": stats,
            "abilities": abilities,
            "moves_mentioned": unique_moves
        })
    return results

def main():
    print("Fetching yakkun.com/ch/ranking.htm ...")
    text = fetch()
    rankings = parse_rankings(text)
    print(f"Found {len(rankings)} pokemon in ranking")
    details = parse_pokemon_details(text, rankings)

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yakkun.com/ch/ranking.htm",
        "format": "singles",
        "pokemon": details
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Wrote data.json with {len(details)} pokemon")

if __name__ == "__main__":
    main()
