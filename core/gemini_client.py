"""Shared Gemini client for EARTHPULSE-X explanations."""

import os

from google import genai


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)
