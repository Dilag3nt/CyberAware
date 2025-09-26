import os
import time
import random
import logging
import psycopg2
import psycopg2.extras
import hashlib
from flask import Blueprint, jsonify
import requests
import urllib.request
import urllib.error
import feedparser
import re
import json
from datetime import datetime, timezone, timedelta
import bleach
from collections import defaultdict
from apscheduler.schedulers.background import BackgroundScheduler
from utils import get_db_conn
from social import post_to_x

content_bp = Blueprint('content', __name__)

XAI_API_URL = os.getenv("XAI_API_URL", "https://api.x.ai/v1/chat/completions")
XAI_API_KEY = os.getenv("XAI_API_KEY")
REFRESH_INTERVAL_SECONDS = 14400

scheduler = BackgroundScheduler({'apscheduler.job_defaults.misfire_grace_time': 3600})

def fetch_headlines():
    logging.debug("Entering fetch_headlines")
    feeds = [
        {"url": "https://feeds.feedburner.com/TheHackersNews", "name": "The Hacker News"},
        {"url": "https://krebsonsecurity.com/feed/", "name": "Krebs on Security"},
        {"url": "https://www.darkreading.com/rss.xml", "name": "Dark Reading"},
        {"url": "https://isc.sans.edu/rssfeed.xml", "name": "SANS Internet Storm Center"},
        {"url": "https://www.bleepingcomputer.com/feed/", "name": "BleepingComputer"}
    ]
    max_retries = 3
    all_headlines = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    keywords = ["ransomware", "phishing", "malware", "social engineering", "credential stuffing", "data breach", "exploit", "cybercrime"]
    for feed in feeds:
        rss_url = feed["url"]
        source_name = feed["name"]
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(rss_url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response:
                    if response.getcode() != 200:
                        logging.warning(f"RSS feed {source_name} returned status {response.getcode()} on attempt {attempt + 1}/{max_retries}")
                        if attempt < max_retries - 1:
                            time.sleep(5)
                            continue
                        break
                    feed_data = feedparser.parse(response.read())
                    if not feed_data.entries:
                        logging.warning(f"No entries in RSS feed {source_name} on attempt {attempt + 1}/{max_retries}")
                        if attempt < max_retries - 1:
                            time.sleep(5)
                            continue
                        break
                    for entry in feed_data.entries[:10]:
                        title = entry.get("title", "").strip()
                        desc = bleach.clean(entry.get("summary", ""), tags=[], strip=True)
                        logging.debug(f"Raw description for {title}: {desc[:225]}")
                        match = re.search(r'((?:[A-Z][^\.]*?\.){1,2})(?:\s|$)', desc[:225])
                        description = match.group(1) if match else desc[:225]
                        link = entry.get("link", "")
                        published_date = entry.get("published_parsed")
                        published_date = datetime(*published_date[:6], tzinfo=timezone.utc) if published_date else None
                        contains_keyword = any(kw.lower() in title.lower() or kw.lower() in description.lower() for kw in keywords)
                        if contains_keyword:
                            all_headlines.append({
                                "title": title,
                                "description": description,
                                "link": link,
                                "source": source_name,
                                "published_date": published_date
                            })
                    break
            except urllib.error.HTTPError as e:
                logging.warning(f"HTTP error {e.code} fetching {source_name} RSS on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
            except Exception as e:
                logging.warning(f"Error fetching {source_name} RSS on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
    return all_headlines

def generate_slide_content(headline):
    if not XAI_API_KEY:
        logging.error("XAI_API_KEY is not set, cannot generate slide")
        return None, None
    prompt = (
        f"Headline: {headline['title']}\nDescription: {headline['description']}\nLink: {headline['link']}\n"
        "Generate a concise cyber awareness slide. Title: 1-2 sentence catchy header. "
        "Content: 3-4 bullet points with prevention tips. Keep it simple, actionable, under 200 words."
    )
    try:
        response = requests.post(
            XAI_API_URL,
            headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "grok-beta", "messages": [{"role": "user", "content": prompt}]}
        )
        response.raise_for_status()
        generated = response.json()["choices"][0]["message"]["content"]
        title_match = re.search(r'Title:\s*(.*)', generated)
        content_match = re.search(r'Content:\s*(.*)', generated, re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Cyber Tip"
        content = content_match.group(1).strip() if content_match else "No content generated."
        return title, content
    except Exception as e:
        logging.error(f"Error generating slide for {headline['title']}: {e}")
        return None, None

def generate_quiz_questions(slide_content):
    if not XAI_API_KEY:
        logging.error("XAI_API_KEY is not set, cannot generate quiz")
        return None, None, None, None
    prompt = (
        f"Slide: {slide_content}\nGenerate 1 multiple-choice quiz question. "
        "Format: Question: text\nOptions: JSON array of 4 strings\nCorrect: index (0-3)\nExplanation: brief text."
    )
    try:
        response = requests.post(
            XAI_API_URL,
            headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "grok-beta", "messages": [{"role": "user", "content": prompt}]}
        )
        response.raise_for_status()
        generated = response.json()["choices"][0]["message"]["content"]
        question_match = re.search(r'Question:\s*(.*)', generated)
        options_match = re.search(r'Options:\s*(\[.*?\])', generated, re.DOTALL)
        correct_match = re.search(r'Correct:\s*(\d)', generated)
        explanation_match = re.search(r'Explanation:\s*(.*)', generated, re.DOTALL)
        question = question_match.group(1).strip() if question_match else "Default question?"
        options = json.loads(options_match.group(1)) if options_match else ["A", "B", "C", "D"]
        correct = int(correct_match.group(1)) if correct_match else 0
        explanation = explanation_match.group(1).strip() if explanation_match else "No explanation."
        return question, json.dumps(options), correct, explanation
    except Exception as e:
        logging.error(f"Error generating quiz: {e}")
        return None, None, None, None

def refresh_database():
    logging.info("Starting database refresh")
    headlines = fetch_headlines()
    if not headlines:
        logging.warning("No headlines fetched, skipping refresh")
        return
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            new_headlines = []
            for h in headlines:
                hash_value = hashlib.sha256((h['title'] + h['description']).encode()).hexdigest()
                cur.execute("SELECT id FROM headlines WHERE hash = %s", (hash_value,))
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO headlines (title, description, link, timestamp, source, published_date, hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """, (h['title'], h['description'], h['link'], datetime.now(timezone.utc),
                          h['source'], h['published_date'], hash_value))
                    headline_id = cur.fetchone()[0]
                    new_headlines.append(headline_id)
            if new_headlines:
                for headline_id in random.sample(new_headlines, min(5, len(new_headlines))):
                    cur.execute("SELECT title, description, link FROM headlines WHERE id = %s", (headline_id,))
                    headline = cur.fetchone()
                    title, content = generate_slide_content({"title": headline[0], "description": headline[1], "link": headline[2]})
                    if title and content:
                        cur.execute(
                            "INSERT INTO slides (title, content, headline_id) VALUES (%s, %s, %s) RETURNING id",
                            (title, content, headline_id)
                        )
                        slide_id = cur.fetchone()[0]
                        question, options, correct, explanation = generate_quiz_questions(content)
                        if question:
                            cur.execute(
                                "INSERT INTO quiz (question, options, correct, explanation, slide_id) VALUES (%s, %s, %s, %s, %s)",
                                (question, options, correct, explanation, slide_id)
                            )
            conn.commit()
            logging.info("Database refresh completed")
    except Exception as e:
        logging.error(f"Error in refresh_database: {e}")
        raise

@content_bp.route('/api/latest_refresh', methods=['GET'])
def latest_refresh():
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(timestamp) FROM headlines")
            latest = cur.fetchone()[0]
            timestamp = int(latest.timestamp()) if latest else 0
            return jsonify({"timestamp": timestamp})
    except Exception as e:
        logging.error(f"Error in /api/latest_refresh: {e}")
        return jsonify({"error": "Failed to fetch latest refresh timestamp"}), 500

@content_bp.route('/api/headlines', methods=['GET'])
def get_headlines():
    try:
        with get_db_conn() as conn:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("""
                SELECT title, description, link, source, published_date, timestamp
                FROM headlines ORDER BY timestamp DESC LIMIT 5
            """)
            headlines = [{"title": row['title'], "description": row['description'] or "No description",
                          "link": row['link'] or "#", "source": row['source'],
                          "published_date": row['published_date'].isoformat().replace('+00:00', 'Z') if row['published_date'] else None,
                          "timestamp": row['timestamp'].isoformat().replace('+00:00', 'Z') if row['timestamp'] else None}
                         for row in cur.fetchall()]
        logging.debug(f"Serving headlines: {headlines}")
        return jsonify(headlines)
    except Exception as e:
        logging.error(f"Error in /api/headlines: {e}")
        return jsonify({"error": "Failed to load headlines"}), 500

@content_bp.route('/api/slides', methods=['GET'])
def get_slides():
    try:
        with get_db_conn() as conn:
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute("""
                SELECT slides.title, slides.content, headlines.title as headline_title,
                       headlines.description as headline_description, headlines.link as headline_link,
                       headlines.source as headline_source, headlines.published_date as headline_published_date,
                       headlines.timestamp as headline_timestamp
                FROM slides
                LEFT JOIN headlines ON slides.headline_id = headlines.id
                ORDER BY slides.created_at DESC
                LIMIT 5
            """)
            slides = []
            for row in cur.fetchall():
                slide = {
                    "title": row['title'],
                    "content": row['content']
                }
                if row['headline_title']:
                    slide.update({
                        "headline": {
                            "title": row['headline_title'],
                            "description": row['headline_description'] or "No description",
                            "link": row['headline_link'] or "#",
                            "source": row['headline_source'],
                            "published_date": row['headline_published_date'].isoformat().replace('+00:00', 'Z') if row['headline_published_date'] else None,
                            "timestamp": row['headline_timestamp'].isoformat().replace('+00:00', 'Z') if row['headline_timestamp'] else None
                        }
                    })
                else:
                    slide["headline"] = None
                slides.append(slide)
            logging.debug(f"Serving slides: {slides}")
            return jsonify(slides)
    except Exception as e:
        logging.error(f"Error in /api/slides: {e}")
        return jsonify({"error": "Failed to load slides"}), 500

def start_scheduler():
    logging.info("Starting scheduler for daily refresh and X post")
    try:
        scheduler.remove_all_jobs()
        scheduler.add_job(
            func=refresh_database,
            trigger="interval",
            seconds=REFRESH_INTERVAL_SECONDS,
            max_instances=1,
            id="refresh_database"
        )
        scheduler.add_job(
            func=post_to_x,
            trigger="cron",
            hour=11,
            minute=11,
            timezone="US/Eastern",
            max_instances=1,
            id="post_to_x"
        )
        scheduler.start()
    except Exception as e:
        logging.error(f"Error starting scheduler: {e}")
        raise