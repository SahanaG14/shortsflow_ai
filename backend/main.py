from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "ShortsFlow AI backend is running"}