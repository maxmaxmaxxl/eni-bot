import aiohttp
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup


async def web_search(query: str, num: int = 5) -> list[dict]:
    """Search the web via DuckDuckGo (no API key needed)."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=params) as resp:
            text = await resp.text()

    soup = BeautifulSoup(text, "html.parser")
    results = []
    for result in soup.select(".result")[:num]:
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")
        if title_el:
            results.append({
                "title": title_el.get_text(strip=True),
                "url": title_el.get("href", ""),
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
            })
    return results


async def read_webpage(url: str) -> str:
    """Fetch and extract readable text content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return f"Error: HTTP {resp.status}"
                html = await resp.text()
        except Exception as e:
            return f"Error fetching page: {e}"

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)

    # truncate to keep responses fast
    if len(text) > 8000:
        text = text[:8000] + "\n\n...[truncated]"

    return text


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    url_pattern = r"https?://[^\s<>\"']+|www\.[^\s<>\"']+"
    return re.findall(url_pattern, text)
