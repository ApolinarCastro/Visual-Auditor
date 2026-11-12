import asyncio
from app.scrapers.paris_scraper import ParisScraper

async def main():
    p = ParisScraper(headless=True)
    await p.start()
    await p.navigate('https://www.paris.cl/search?q=nicopoly')
    await asyncio.sleep(4)
    data = await p.page.evaluate('''() => {
        const anchors = Array.from(document.querySelectorAll('a[href]'));
        return anchors.map(a => ({href: a.href, text: a.innerText, cls: a.className}))
                      .filter(x => x.href.includes('nicopoly') || x.href.includes('facet') || x.href.includes('cat') || x.href.includes('mujer'));
    }''')
    print("Found category-like anchors count:", len(data))
    for d in data[:50]:
        print(d)
    await p.stop()

if __name__ == '__main__':
    asyncio.run(main())
