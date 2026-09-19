import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///movies.db")

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

RATINGS = {
    "💀": 1,
    "😤": 2,
    "😑": 3,
    "😐": 4,
    "🙂": 5,
    "👍": 6,
    "😊": 7,
    "🔥": 8,
    "⭐": 9,
    "💎": 10,
}
