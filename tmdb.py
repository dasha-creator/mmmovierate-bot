import aiohttp
from config import TMDB_API_KEY, TMDB_BASE_URL, TMDB_IMAGE_BASE

async def search_multi(query: str, page: int = 1) -> dict:
    """Search movies, TV shows and anime"""
    url = f"{TMDB_BASE_URL}/search/multi"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "page": page,
        "language": "ru-RU",
        "include_adult": "false",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
    
    results = []
    for item in data.get("results", []):
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv"):
            continue
        
        title = item.get("title") or item.get("name") or "Без названия"
        original_title = item.get("original_title") or item.get("original_name") or ""
        year = ""
        date = item.get("release_date") or item.get("first_air_date") or ""
        if date:
            year = date[:4]
        
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
            "genre_ids": item.get("genre_ids", []),
        })
    
    return {
        "results": results[:8],
        "total_pages": data.get("total_pages", 1),
        "page": page,
    }

async def get_details(tmdb_id: int, media_type: str) -> dict:
    """Get full details for a movie or TV show"""
    url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU",
        "append_to_response": "genres",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            item = await resp.json()
    
    title = item.get("title") or item.get("name") or "Без названия"
    original_title = item.get("original_title") or item.get("original_name") or ""
    date = item.get("release_date") or item.get("first_air_date") or ""
    year = date[:4] if date else ""
    genres = [g["name"] for g in item.get("genres", [])]
    
    return {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": title,
        "original_title": original_title,
        "year": year,
        "overview": item.get("overview", "Описание недоступно."),
        "poster_path": item.get("poster_path"),
        "poster_url": f"{TMDB_IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else None,
        "vote_average": item.get("vote_average", 0),
        "genres": genres,
        "runtime": item.get("runtime") or item.get("episode_run_time", [None])[0] if item.get("episode_run_time") else None,
        "number_of_seasons": item.get("number_of_seasons"),
    }

def format_media_type(media_type: str) -> str:
    return "🎬 Фильм" if media_type == "movie" else "📺 Сериал / Аниме"


async def get_popular() -> list:
    """Популярные фильмы для рандомного когда вишлист пустой"""
    url = f"{TMDB_BASE_URL}/movie/popular"
    params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "page": 1}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
    results = []
    for item in data.get("results", [])[:20]:
        results.append({
            "tmdb_id": item["id"],
            "media_type": "movie",
            "title": item.get("title", ""),
            "poster_path": item.get("poster_path"),
        })
    return results
