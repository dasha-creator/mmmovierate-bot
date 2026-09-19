import aiohttp
from config import TMDB_API_KEY, TMDB_BASE_URL, TMDB_IMAGE_BASE

TIMEOUT = aiohttp.ClientTimeout(total=10)

async def search_multi(query: str, page: int = 1) -> dict:
    url = f"{TMDB_BASE_URL}/search/multi"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "page": page,
        "language": "ru-RU",
        "include_adult": "false",
    }
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
    except Exception as e:
        print(f"TMDB search error: {e}")
        return {"results": [], "total_pages": 1, "page": 1}

    results = []
    for item in data.get("results", []):
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        title = item.get("title") or item.get("name") or "Без названия"
        original_title = item.get("original_title") or item.get("original_name") or ""
        date = item.get("release_date") or item.get("first_air_date") or ""
        year = date[:4] if date else ""
        results.append({
            "tmdb_id": item["id"],
            "media_type": media_type,
            "title": title,
            "original_title": original_title,
            "year": year,
            "overview": item.get("overview", ""),
            "poster_path": item.get("poster_path"),
            "poster_url": f"{TMDB_IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else None,
            "vote_average": item.get("vote_average", 0),
        })

    return {"results": results[:8], "total_pages": data.get("total_pages", 1), "page": page}


async def get_details(tmdb_id: int, media_type: str) -> dict:
    url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "append_to_response": "genres"}
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(url, params=params) as resp:
                item = await resp.json()
    except Exception as e:
        print(f"TMDB details error: {e}")
        return {
            "tmdb_id": tmdb_id, "media_type": media_type,
            "title": "Неизвестно", "original_title": "", "year": "",
            "overview": "Не удалось загрузить описание.",
            "poster_path": None, "poster_url": None,
            "vote_average": 0, "genres": [],
        }

    title = item.get("title") or item.get("name") or "Без названия"
    original_title = item.get("original_title") or item.get("original_name") or ""
    date = item.get("release_date") or item.get("first_air_date") or ""
    year = date[:4] if date else ""
    genres = [g["name"] for g in item.get("genres", [])]

    return {
        "tmdb_id": tmdb_id, "media_type": media_type,
        "title": title, "original_title": original_title, "year": year,
        "overview": item.get("overview", "Описание недоступно."),
        "poster_path": item.get("poster_path"),
        "poster_url": f"{TMDB_IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else None,
        "vote_average": item.get("vote_average", 0),
        "genres": genres,
    }


async def get_popular() -> list:
    url = f"{TMDB_BASE_URL}/movie/popular"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "page": 1}
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
    except Exception as e:
        print(f"TMDB popular error: {e}")
        return []

    results = []
    for item in data.get("results", [])[:20]:
        results.append({
            "tmdb_id": item["id"],
            "media_type": "movie",
            "title": item.get("title", ""),
            "poster_path": item.get("poster_path"),
        })
    return results


def format_media_type(media_type: str) -> str:
    return "🎬 Фильм" if media_type == "movie" else "📺 Сериал / Аниме"
