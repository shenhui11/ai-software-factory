import anyio
import httpx
from fastapi import FastAPI, status

# 创建简单的测试应用
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
async def health():
    return {"status": "ok"}

def test_root():
    async def runner():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/")
            assert response.status_code == status.HTTP_200_OK
            assert response.json() == {"message": "Hello World"}

    anyio.run(runner)

def test_health():
    async def runner():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/health")
            assert response.status_code == status.HTTP_200_OK
            assert response.json() == {"status": "ok"}

    anyio.run(runner)
