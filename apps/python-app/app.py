from flask import Flask

app = Flask(__name__)


@app.get("/")
def home():
    return {
        "message": "Hello from our deployment platform",
        "version": "3.0"
    }


@app.get("/health")
def health():
    return {
        "status": "unhealthy",
        "version": "4.0"
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
