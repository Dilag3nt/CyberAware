import logging
from flask import Blueprint, jsonify
import requests
import os

phish_bp = Blueprint('phish', __name__)

XAI_API_URL = os.getenv("XAI_API_URL", "https://api.x.ai/v1/chat/completions")
XAI_API_KEY = os.getenv("XAI_API_KEY")

@phish_bp.route('/api/phish/generate', methods=['GET'])
def generate_phish():
    if not XAI_API_KEY:
        logging.error("XAI_API_KEY is not set, cannot generate phishing simulation")
        return jsonify({"error": "API key not configured"}), 500
    prompt = (
        "Generate a realistic phishing simulation scenario as an HTML-formatted mock (email or SMS) "
        "aimed at stealing credentials or installing malware. Include 3-5 subtle red flags like urgency, "
        "mismatched domains, typos, or suspicious links. Make it believable, e.g., spoofing a bank alert, "
        "package delivery, password reset, or prize notification. Output only the raw HTML content for "
        "direct rendering, with interactive elements (e.g., hoverable links/images) and no explanations."
    )
    try:
        response = requests.post(
            XAI_API_URL,
            headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "grok-beta", "messages": [{"role": "user", "content": prompt}]}
        )
        response.raise_for_status()
        generated_html = response.json()["choices"][0]["message"]["content"]
        return jsonify({"html": generated_html})
    except Exception as e:
        logging.error(f"Error generating phish: {e}")
        return jsonify({"html": "<p>Phishing simulation temporarily unavailable. Please try again later.</p>"}), 200