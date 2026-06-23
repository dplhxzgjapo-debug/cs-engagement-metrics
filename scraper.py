#!/usr/bin/env python3
# scraper debug2 03:39
"""Scrape yakkun.com Pokemon Champions singles ranking + full Pokedex, output data.json"""
import re, json, urllib.request, datetime, math

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TYPE_ID_MAP = {
    '0': 'normal', '1': 'fighting', '2': 'flying', '3': 'poison',
    '4': 'ground', '5': 'rock', '6': 'bug', '7': 'ghost',
    '8': 'steel', '9': 'fire', '10': 'water', '11': 'grass',
    '12': 'electric', '13': 'psychic', '14': 'ice', '15': 'dragon',
    '16': 'dark', '17': 'fairy'
}

def max_speed_lv50(base):
    return math.floor(((base * 2 + 31 + 63) * 50 / 100 + 5) * 1.1)

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("euc-jp", errors="replace")

def fetch_utf8(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")

def parse_pokedb_rankings(html):
    """champs.pokedb.tokyo の使用率テーブルを抽出。
    多様な構造に耐えるよう、各 <tr> から rank/name/usage を緩く拾う。"""
    rankings = []
    # 各行を取り出してパース
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for row in rows:
        # rank: <td> の最初の整数
        rm = re.search(r'<t[hd][^>]*>\s*(\d{1,3})\s*</t[hd]>', row)
        # name: pokemon 詳細ページへのリンクテキスト
        nm = re.search(r'/pokemon/show/[^"\']+["\'][^>]*>\s*([^<>]+?)\s*</a>', row)
        # usage: X.X% パターン
        um = re.search(r'(\d+\.\d+)\s*%', row)
        if not (rm and nm): continue
        rank = int(rm.group(1))
        name = nm.group(1).strip()
        usage = float(um.group(1)) if um else None
        if 1 <= rank <= 200 and name:
            rankings.append({"rank": rank, "name": name, "usage_rate": usage})
    # dedup by rank (preserve first)
    seen, out = set(), []
    for r in rankings:
        if r['rank'] in seen: continue
        seen.add(r['rank'])
        out.append(r)
    return sorted(out, key=lambda x: x['rank'])

def parse_rankings(text):
    matches = re.findall(r'(\d+)\u4f4d: ([^<"]+)', text)
    seen, out = set(), []
    for rank, name in matches:
        if rank not in seen:
            seen.add(rank)
            out.append({"rank": int(rank), "name": name.strip()})
    return out

def parse_pokemon_details(text, rankings):
    results = []
    for entry in rankings:
        rank, name = entry["rank"], entry["name"]
        header = f'{rank}\u4f4d: {name}</h2>'
        start = text.find(header)
        if start < 0:
            results.append({**entry, "types": [], "stats": {}, "abilities": [], "moves_mentioned": []})
            continue
        next_h2 = text.find('<h2 id="', start + len(header))
        chunk = text[start:next_h2] if next_h2 > 0 else text[start:start+8000]
        types = re.findall(r'alt="([^"]+)"[^>]*/>\s*</li>', chunk)
        type_map = {
            "\u30ce\u30fc\u30de\u30eb":"normal","\u307b\u306e\u304a":"fire","\u307f\u305a":"water","\u304f\u3055":"grass",
            "\u3067\u3093\u304d":"electric","\u3053\u304a\u308a":"ice","\u304b\u304f\u3068\u3046":"fighting","\u3069\u304f":"poison",
            "\u3058\u3081\u3093":"ground","\u3072\u3053\u3046":"flying","\u30a8\u30b9\u30d1\u30fc":"psychic","\u3080\u3057":"bug",
            "\u3044\u308f":"rock","\u30b4\u30fc\u30b9\u30c8":"ghost","\u30c9\u30e9\u30b4\u30f3":"dragon","\u3042\u304f":"dark",
            "\u306f\u304c\u306d":"steel","\u30d5\u30a7\u30a2\u30ea\u30fc":"fairy"
        }
        types_en = [type_map.get(t, t) for t in types if t in type_map]
        stats = {}
        stat_matches = re.findall(r'<dt>(HP|\u653b\u6483|\u9632\u5fa1|\u7279\u653b|\u7279\u9632|\u7d20\u65e9)</dt><dd[^>]*>(\d+)</dd>', chunk)
        stat_keys = {"HP":"hp","\u653b\u6483":"atk","\u9632\u5fa1":"def","\u7279\u653b":"spa","\u7279\u9632":"spd","\u7d20\u65e9":"spe"}
        for label, val in stat_matches:
            stats[stat_keys.get(label, label)] = int(val)
        abilities = re.findall(r'class="ability">([^<]+)</a>', chunk)
        moves = re.findall(r'class="move">([^<]+)</a>', chunk)
        seen_m = set()
        unique_moves = [m for m in moves if m not in seen_m and not seen_m.add(m)]
        results.append({**entry, "types": types_en, "stats": stats, "abilities": abilities, "moves_mentioned": unique_moves})
    return results

def parse_pokedex(text):
    items = re.findall(
        r'<li\s+data-id="([^"]*)"[^>]*?data-types="([^"]+)"([^>]*)>(.*?)</li>',
        text, re.DOTALL
    )
    available = []
    megas = []
    for did, dtypes, rest, content in items:
        if 'nodata' in rest:
            continue
        name_m = re.search(r'icon32_sp[^>]*></i>([^<]+)</a>', content)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        stats_m = re.findall(r'<span>(\d+)</span>', content)
        if len(stats_m) < 6:
            continue
        types = [TYPE_ID_MAP.get(t, t) for t in dtypes.split(',')]
        hp, atk, df, spa, spd_stat, spe = [int(s) for s in stats_m[:6]]
        is_ghost = 'ghost' in types
        # \u30e1\u30ac\u306f\u5225\u914d\u5217\u306b
        if name.startswith("\u30e1\u30ac"):
            megas.append({
                "name": name,
                "types": types,
                "spe_base": spe,
                "spe_max": max_speed_lv50(spe),
                "stats": {"hp":hp,"atk":atk,"def":df,"spa":spa,"spd":spd_stat,"spe":spe},
                "ghost": is_ghost
            })
            continue
        if df + spd_stat >= 200 and hp >= 80:
            cat = 'wall'
        elif atk >= 100 and atk >= spa:
            cat = 'phy_atk'
        elif spa >= 100:
            cat = 'spe_atk'
        elif hp + df + spd_stat >= 260:
            cat = 'support'
        elif atk >= spa:
            cat = 'phy_atk'
        else:
            cat = 'spe_atk'
        available.append({
            "name": name,
            "types": types,
            "spe_base": spe,
            "spe_max": max_speed_lv50(spe),
            "cat": cat,
            "ghost": is_ghost
        })
    return available, megas

def main():
    print("Fetching ranking...")
    ranking_text = fetch("https://yakkun.com/ch/ranking.htm")
    rankings = parse_rankings(ranking_text)
    print(f"Found {len(rankings)} ranked")
    details = parse_pokemon_details(ranking_text, rankings)

    print("Fetching pokedex...")
    pokedex_text = fetch("https://yakkun.com/ch/zukan/offer/")
    all_pokemon, all_megas = parse_pokedex(pokedex_text)
    print(f"Found {len(all_pokemon)} available (excl. megas) + {len(all_megas)} megas")

    # champs.pokedb.tokyo から M-3 シングル使用率を追加取得 (TOP100まで)
    print("Fetching pokedb rankings...")
    rankings_pokedb_singles = []
    rankings_pokedb_doubles = []
    pokedb_debug = {}
    try:
        html = fetch_utf8("https://champs.pokedb.tokyo/pokemon/list?season=3&rule=0")
        rankings_pokedb_singles = parse_pokedb_rankings(html)
        # デバッグ情報: HTML長と構造ヒント
        pokedb_debug["singles_html_len"] = len(html)
        pokedb_debug["has_tr"] = html.count("<tr")
        pokedb_debug["has_pokemon_show_link"] = html.count("/pokemon/show/")
        pokedb_debug["has_table"] = html.count("<table")
        pokedb_debug["has_react_root"] = ("__NEXT_DATA__" in html) or ("react-root" in html) or ('id="__next"' in html)
        # 最初の /pokemon/show/ リンクの前後 2000 文字を切り出し
        idx = html.find('href="/pokemon/show/')
        if idx > 0:
            pokedb_debug["context_before_first_link"] = html[max(0,idx-1500):idx]
            pokedb_debug["context_after_first_link"] = html[idx:idx+1500]
        print(f"pokedb singles: {len(rankings_pokedb_singles)} entries, html_len={len(html)}")
        print(f"  debug: {pokedb_debug}")
    except Exception as e:
        print(f"pokedb singles fetch failed: {e}")
        pokedb_debug["error"] = str(e)
    try:
        html = fetch_utf8("https://champs.pokedb.tokyo/pokemon/list?season=3&rule=1")
        rankings_pokedb_doubles = parse_pokedb_rankings(html)
        print(f"pokedb doubles: {len(rankings_pokedb_doubles)} entries")
    except Exception as e:
        print(f"pokedb doubles fetch failed: {e}")

    output = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "yakkun.com + champs.pokedb.tokyo",
        "format": "singles",
        "pokemon": details,
        "all_pokemon": all_pokemon,
        "all_megas": all_megas,
        "rankings_pokedb_singles": rankings_pokedb_singles,
        "rankings_pokedb_doubles": rankings_pokedb_doubles,
        "pokedb_debug": pokedb_debug
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Done: yakkun {len(details)} ranked + {len(all_pokemon)} non-mega + {len(all_megas)} megas / pokedb singles {len(rankings_pokedb_singles)} / doubles {len(rankings_pokedb_doubles)}")

if __name__ == "__main__":
    main()
