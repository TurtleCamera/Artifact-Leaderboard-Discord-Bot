import aiohttp
import asyncio

async def test_easyocr_api():
    url = "https://api.easyocr.org/ocr"

    with open("test.png", "rb") as f:
        image_bytes = f.read()

    data = aiohttp.FormData()
    data.add_field("file", image_bytes, filename="test.png", content_type="image/png")
    data.add_field("lang", "en,fr")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            print("Status:", resp.status)
            result = await resp.json()
            print("Response JSON:", result)

asyncio.run(test_easyocr_api())
