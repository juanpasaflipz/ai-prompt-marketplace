#!/usr/bin/env python3
"""
Simple test server to verify basic setup
"""

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="AI Prompt Marketplace - Test")

@app.get("/")
def read_root():
    return {"message": "AI Prompt Marketplace API is starting up!", "status": "ok"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "ai-prompt-marketplace"}

if __name__ == "__main__":
    print("Starting test server on http://localhost:8000")
    print("Visit http://localhost:8000/docs for API documentation")
    uvicorn.run(app, host="0.0.0.0", port=8000)