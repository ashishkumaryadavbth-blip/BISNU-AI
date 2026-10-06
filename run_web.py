import uvicorn

from bisnu_x.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "bisnu_x.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        workers=1,
    )
