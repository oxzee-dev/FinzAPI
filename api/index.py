"""
Vercel entry point.
Mangum wraps the FastAPI ASGI app to run as a Vercel/AWS Lambda handler.
"""
from mangum import Mangum
from main import app

handler = Mangum(app, lifespan="off")
