from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
