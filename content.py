from flask import Blueprint, jsonify
import requests
import urllib.request
import urllib.error
import feedparser
import re
import json
import logging
import datetime
import bleach
from collections import defaultdict
from datetime import timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from utils import get_db_conn

content_bp = Blueprint('content', __name__)

XAI_API_URL = "https://api.x.ai/v1/chat/completions"
XAI_API_KEY = os.getenv("XAI_API_KEY")
RSS_FEEDS = [
    {"url": "https://feeds.feedburner.com/TheHackersNews", "name": "The Hacker News"},
    {"url": "https://krebsonsecurity.com/feed/", "name": "Krebs on Security"},
    {"url": "https://www.darkreading.com/rss.xml", "name": "Dark Reading"},
    {"url": "https://isc.sans.edu/rssfeed.xml", "name": "SANS Internet Storm Center"},
    {"url": "https://www.bleepingcomputer.com/feed/", "name": "BleepingComputer"}
]
REFRESH_INTERVAL_SECONDS = 14400

scheduler = BackgroundScheduler({'apscheduler.job_defaults.misfire_grace_time': 3600})

def fetch_headlines():
    logging.debug("Entering fetch_headlines")
    feeds = RSS_FEEDS
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
                        description = match.group(1) if match else desc[:225].rstrip()
                        if len(description) < 180:
                            extended_match = re.search(r'((?:[A-Z][^\.]*?\.){1,4})(?:\s|$)', desc[:225])
                            description = extended_match.group(1) if extended_match else desc[:225].rstrip()
                        if len(desc) > len(description) and not description.endswith('.'):
                            description += '...'
                        if len(description) < 100:
                            description = desc[:225].rstrip() + ('...' if len(desc) > 225 else '')
                        link = entry.get("link", "#").strip()
                        source = source_name
                        published_date = (datetime.datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                                         if entry.get('published_parsed')
                                         else None)
                        timestamp = datetime.datetime.now(timezone.utc)
                        if any(keyword in title.lower() or keyword in description.lower() for keyword in keywords):
                            all_headlines.append({
                                "title": title,
                                "description": description,
                                "link": link,
                                "timestamp": timestamp,
                                "source": source,
                                "published_date": published_date
                            })
                    logging.debug(f"Fetched {len(feed_data.entries[:10])} entries from {source_name}: {[entry.title for entry in feed_data.entries[:10]]}")
                    break
            except urllib.error.HTTPError as e:
                logging.error(f"HTTP error fetching RSS feed {source_name} on attempt {attempt + 1}/{max_retries}: {e.code} {e.reason}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                break
            except urllib.error.URLError as e:
                logging.error(f"URL error fetching RSS feed {source_name} on attempt {attempt + 1}/{max_retries}: {e.reason}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                break
            except Exception as e:
                logging.error(f"Unexpected error fetching RSS feed {source_name} on attempt {attempt + 1}/{max_retries}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                break
    grouped = defaultdict(list)
    for headline in all_headlines:
        grouped[headline['source']].append(headline)
    selected = []
    sources = list(grouped.keys())
    random.shuffle(sources)
    while len(selected) < 5 and sources:
        for source in sources[:]:
            if grouped[source]:
                selected.append(grouped[source].pop(0))
                if len(selected) >= 5:
                    break
            else:
                sources.remove(source)
    if len(selected) < 5:
        logging.warning(f"Only {len(selected)} headlines found; using available.")
    unique_headlines = []
    seen_titles = set()
    for headline in selected:
        if headline["title"] not in seen_titles:
            unique_headlines.append(headline)
            seen_titles.add(headline["title"])
    logging.debug(f"Returning {len(unique_headlines)} unique headlines: {[h['title'] for h in unique_headlines]}")
    return unique_headlines[:5]

def call_xai_api(prompt):
    import os
    from dotenv import load_dotenv
    load_dotenv()
    headers = {"Authorization": f"Bearer {os.getenv('XAI_API_KEY')}", "Content-Type": "application/json"}
    data = {"model": "grok-3-mini", "messages": [{"role": "user", "content": prompt}]}
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(XAI_API_URL, headers=headers, json=data, timeout=120)
            logging.debug(f"xAI API status: {response.status_code} at {datetime.datetime.now(timezone.utc)}")
            logging.debug(f"xAI API response: {response.text}")
            response.raise_for_status()
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content.startswith('```json'):
                content = content[7:-3].strip()
            return content
        except requests.exceptions.Timeout:
            logging.error(f"xAI API timeout on attempt {attempt + 1}/{max_retries}: Read timed out. (read timeout=120) at {datetime.datetime.now(timezone.utc)}")
            if attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            return None
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"xAI API HTTP error on attempt {attempt + 1}/{max_retries}: {http_err} at {datetime.datetime.now(timezone.utc)}, response: {response.text if 'response' in locals() else 'No response'}")
            if attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            return None
        except Exception as e:
            logging.error(f"xAI API unexpected error on attempt {attempt + 1}/{max_retries}: {str(e)} at {datetime.datetime.now(timezone.utc)}")
            if attempt < max_retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            return None

def parse_slides_response(response_text):
    slides = []
    if not response_text or not isinstance(response_text, str):
        logging.debug(f"Empty or invalid slide response: {response_text}")
        return slides
    match = re.search(r'Slide \d+[: ]*\n', response_text)
    if not match:
        logging.debug(f"No Slide marker found in response: {response_text[:200]}...")
        return slides
    content = response_text[match.start():]
    slide_sections = re.split(r'Slide \d+[: ]*\n', content, flags=re.DOTALL)
    for i, section in enumerate(slide_sections[1:], 1):
        if not section.strip():
            continue
        section_text = section.strip()
        lines = [line.strip() for line in section_text.split('\n') if line.strip()]
        logging.debug(f"Raw lines for Slide {i}: {lines}")
        title_match = re.search(r'\*\*Title:\*\* ([^\n]*?)(?=\s*$|\s*\n)', section_text)
        title = title_match.group(1).strip() if title_match else f"Slide {i}"
        content_text = re.sub(r'\*\*Title:\*\*.*?\n', '', section_text, 1).strip()
        if i == 1:
            content = re.sub(r'^\s*Content:\s*\n?', '', content_text, flags=re.DOTALL).strip()
            content = re.sub(r'^\s*and a concise summary of this week\'s key cyber events:?\s*', '', content).strip()
            content = content.rstrip('-')
        elif 2 <= i <= 4:
            content = content_text.rstrip('-')
        elif i == 5:
            content = content_text.rstrip('-')
        else:
            continue
        logging.debug(f"Parsed Slide {i}: Title='{title}', Content='{content}'")
        slides.append({"title": title, "content": content})
    if len(slides) != 5:
        logging.error(f"Slides parsing failed, got {len(slides)} slides: {slides}")
    return slides[:5]

def parse_quiz_response(response_text):
    quiz = []
    if not response_text:
        logging.debug("Empty quiz response")
        return quiz
    try:
        logging.debug(f"Raw quiz response: {response_text}")
        quiz_data = json.loads(response_text)
        for quiz_item in quiz_data:
            if (isinstance(quiz_item, dict) and 'question' in quiz_item and 'options' in quiz_item and
                'correct' in quiz_item and 'explanation' in quiz_item and
                isinstance(quiz_item['options'], list) and len(quiz_item['options']) >= 2 and
                isinstance(quiz_item['correct'], int) and 0 <= quiz_item['correct'] < len(quiz_item['options'])):
                clean_options = [re.sub(r'^\s*[A-D1-4]\.\s*', '', opt).strip() for opt in quiz_item['options']]
                is_true_false = (clean_options[quiz_item['correct']].lower() in ['true', 'false'] or
                                 quiz_item['question'].lower().endswith('(true/false)') or
                                 quiz_item['question'].lower().startswith('true or false:'))
                if is_true_false:
                    quiz_item['question'] = quiz_item['question'].replace('(True/False)', '').strip()
                    if not quiz_item['question'].lower().startswith('true or false:'):
                        quiz_item['question'] = f"True or False: {quiz_item['question']}"
                    quiz_item['options'] = ['True', 'False']
                    quiz_item['correct'] = 0 if clean_options[quiz_item['correct']].lower() == 'true' else 1
                    logging.debug(f"Processed True/False question: {quiz_item['question']}, options: {quiz_item['options']}, correct: {quiz_item['correct']}")
                else:
                    quiz_item['options'] = clean_options
                    logging.debug(f"Processed non-True/False question: {quiz_item['question']}, options: {quiz_item['options']}, correct: {quiz_item['correct']}")
                quiz.append(quiz_item)
            else:
                logging.warning(f"Invalid quiz item: {quiz_item}")
        logging.debug(f"Parsed quiz: {quiz}")
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error in quiz response: {e}")
        return quiz
    return quiz[:5]

def should_refresh():
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT timestamp FROM headlines ORDER BY timestamp DESC LIMIT 1")
        last_refresh = cur.fetchone()
        if not last_refresh:
            return True
        return (datetime.datetime.now(timezone.utc).timestamp() - last_refresh[0].timestamp()) >= REFRESH_INTERVAL_SECONDS

def refresh_database():
    max_attempts = 3
    fallback_headlines = [
        {"title": "Phishing Attacks on the Rise", "description": "Recent increase in phishing attempts targeting remote workers.", "link": "#", "timestamp": datetime.datetime.now(timezone.utc), "source": "Fallback Source", "published_date": None},
        {"title": "Ransomware Threat Alert", "description": "New ransomware variant detected in corporate networks.", "link": "#", "timestamp": datetime.datetime.now(timezone.utc), "source": "Fallback Source", "published_date": None},
        {"title": "Data Breach at Major Firm", "description": "Sensitive data exposed in recent security breach.", "link": "#", "timestamp": datetime.datetime.now(timezone.utc), "source": "Fallback Source", "published_date": None},
        {"title": "Zero-Day Vulnerability Found", "description": "Critical software flaw discovered, patches pending.", "link": "#", "timestamp": datetime.datetime.now(timezone.utc), "source": "Fallback Source", "published_date": None},
        {"title": "Cybersecurity Training Urged", "description": "Experts recommend regular employee training to combat threats.", "link": "#", "timestamp": datetime.datetime.now(timezone.utc), "source": "Fallback Source", "published_date": None}
    ]
    for attempt in range(max_attempts):
        logging.info(f"Refresh database attempt {attempt + 1}/{max_attempts} started at {datetime.datetime.now(timezone.utc)}")
        try:
            with get_db_conn() as conn:
                cur = conn.cursor()
                start_time = datetime.datetime.now(timezone.utc)
                logging.debug(f"Headlines fetch started at {start_time}")
                new_headlines = []
                headline_ids = []
                try:
                    cur.execute("SELECT COUNT(*) FROM headlines WHERE timestamp > %s",
                                (datetime.datetime.now(timezone.utc) - datetime.timedelta(seconds=REFRESH_INTERVAL_SECONDS/2),))
                    recent_headline_count = cur.fetchone()[0]
                    if recent_headline_count >= 5:
                        logging.info(f"Skipping headline fetch at {datetime.datetime.now(timezone.utc)}, {recent_headline_count} recent headlines exist.")
                        cur.execute("SELECT id, title, description, link, timestamp, source, published_date FROM headlines ORDER BY timestamp DESC LIMIT 5")
                        rows = cur.fetchall()
                        new_headlines = [{"title": row[1], "description": row[2], "link": row[3], "timestamp": row[4], "source": row[5], "published_date": row[6]} for row in rows]
                        headline_ids = [row[0] for row in rows]
                        logging.debug(f"Database headlines fetched: {[row[1] for row in rows]}")
                    else:
                        new_headlines = fetch_headlines()
                        logging.debug(f"Fetched headlines: {[h['title'] for h in new_headlines]}")
                        if len(new_headlines) < 5:
                            logging.warning(f"Only {len(new_headlines)} headlines fetched at {datetime.datetime.now(timezone.utc)}, supplementing with recent database headlines.")
                            cur.execute("SELECT id, title, description, link, timestamp, source, published_date FROM headlines ORDER BY timestamp DESC LIMIT %s",
                                        (5 - len(new_headlines),))
                            rows = cur.fetchall()
                            new_headlines.extend([{"title": row[1], "description": row[2], "link": row[3], "timestamp": row[4], "source": row[5], "published_date": row[6]} for row in rows])
                        if len(new_headlines) < 5:
                            logging.warning(f"Insufficient headlines ({len(new_headlines)}) at {datetime.datetime.now(timezone.utc)}, using fallback headlines.")
                            new_headlines.extend(fallback_headlines[:5 - len(new_headlines)])
                        for h in new_headlines[:5]:
                            content_hash = hashlib.md5((h["title"] + h["description"] + h["link"]).encode('utf-8')).hexdigest()
                            cur.execute("SELECT id FROM headlines WHERE hash = %s", (content_hash,))
                            existing = cur.fetchone()
                            if existing:
                                logging.debug(f"Duplicate headline found: {h['title']}, using existing ID {existing[0]}")
                                headline_ids.append(existing[0])
                            else:
                                cur.execute("INSERT INTO headlines (title, description, link, timestamp, source, published_date, hash) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                                            (h["title"], h["description"], h["link"], h["timestamp"], h["source"], h["published_date"], content_hash))
                                headline_ids.append(cur.fetchone()[0])
                        conn.commit()
                        logging.debug(f"Headlines stored at {datetime.datetime.now(timezone.utc)}, stored {len(new_headlines[:5])} headlines: {[h['title'] for h in new_headlines[:5]]}")
                except psycopg2.Error as e:
                    logging.error(f"Database error while storing headlines: {e}")
                    conn.rollback()
                    raise
                headlines_titles = [h["title"] for h in new_headlines[:5]]
                logging.debug(f"Headlines used for prompt: {headlines_titles}")
                slides_prompt = f"Provide 5 slides based on these headlines: {', '.join(headlines_titles)}. Format each slide strictly as follows:\n"
                for i in range(5):
                    slides_prompt += f"- Slide {i+1}\n **Title:** {headlines_titles[i] if i < len(headlines_titles) else 'No data'}\n Threat: [brief threat description]\n Safety tips: [brief safety advice]\n"
                slides_prompt += "Use plain text, no HTML tags. Start each slide with 'Slide N' followed by a newline. Use exactly '**Title:**' for all titles, followed by a newline, then the specified content with sections (Threat, Safety tips) separated by newlines. Ensure all titles use '**Title:**' consistently."
                logging.debug(f"Slides prompt sent at {datetime.datetime.now(timezone.utc)}: {slides_prompt}")
                slides_response = call_xai_api(slides_prompt)
                new_slides = []
                if slides_response:
                    new_slides = parse_slides_response(slides_response)
                    if not (new_slides and len(new_slides) == 5 and all(isinstance(s, dict) and 'title' in s and 'content' in s for s in new_slides)):
                        logging.error(f"Invalid slides response at {datetime.datetime.now(timezone.utc)}: {slides_response}")
                        return
                else:
                    logging.error(f"No slides response at {datetime.datetime.now(timezone.utc)}")
                    return
                try:
                    current_time = datetime.datetime.now(timezone.utc)
                    slide_ids = []
                    for i, s in enumerate(new_slides):
                        cur.execute("INSERT INTO slides (title, content, headline_id, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
                                    (s["title"], s["content"], headline_ids[i], current_time))
                        slide_ids.append(cur.fetchone()[0])
                    conn.commit()
                    logging.debug(f"Slides stored at {datetime.datetime.now(timezone.utc)}")
                except psycopg2.Error as e:
                    logging.error(f"Database error while storing slides: {e}")
                    conn.rollback()
                    raise
                logging.debug(f"Quiz prompt sent at {datetime.datetime.now(timezone.utc)}")
                quiz_prompt = f"Generate exactly one question per slide for the 5 slides: {json.dumps(new_slides, separators=(',', ':'))}. Ensure variety: 2 multiple-choice, 1 true/false, 2 scenario-based across all. For true/false, prefix question with 'True or False:' and options: ['True', 'False']. For multiple-choice and scenario-based, provide exactly 4 options without any prefixes (e.g., no 'A. ', 'B. '). Return JSON array in slide order: {{'question':str,'options':[str,...],'correct':int,'explanation':str}}. Ensure 'correct' is a valid index."
                quiz_response = call_xai_api(quiz_prompt)
                if quiz_response:
                    new_quiz = parse_quiz_response(quiz_response)
                    if new_quiz and len(new_quiz) == 5 and all(isinstance(q, dict) and 'question' in q and 'options' in q and 'correct' in q and 'explanation' in q for q in new_quiz):
                        try:
                            current_time = datetime.datetime.now(timezone.utc)
                            for i, q in enumerate(new_quiz):
                                cur.execute("INSERT INTO quiz (question, options, correct, explanation, created_at, slide_id) VALUES (%s, %s, %s, %s, %s, %s)",
                                            (q["question"], json.dumps(q["options"]), q["correct"], q["explanation"], current_time, slide_ids[i]))
                            conn.commit()
                            logging.debug(f"New quiz inserted at {datetime.datetime.now(timezone.utc)}")
                        except psycopg2.Error as e:
                            logging.error(f"Database error while inserting quiz: {e}")
                            conn.rollback()
                            raise
                    else:
                        logging.error(f"Invalid quiz response at {datetime.datetime.now(timezone.utc)}: {quiz_response}")
                else:
                    logging.error(f"No quiz response at {datetime.datetime.now(timezone.utc)}")
                try:
                    cleanup_time = datetime.datetime.now(timezone.utc) - datetime.timedelta(days=1)
                    cur.execute("ALTER TABLE slides DROP CONSTRAINT IF EXISTS slides_headline_id_fkey")
                    cur.execute("ALTER TABLE quiz DROP CONSTRAINT IF EXISTS quiz_slide_id_fkey")
                    cur.execute("SELECT id, headline_id FROM slides ORDER BY created_at DESC LIMIT 5")
                    recent_slides = cur.fetchall()
                    logging.debug(f"Recent slides fetched: {len(recent_slides)} slides")
                    recent_slide_ids = [row[0] for row in recent_slides] or [0]
                    recent_headline_ids = [row[1] for row in recent_slides if row[1] is not None] or [0]
                    logging.debug(f"Recent slide IDs: {recent_slide_ids}, Recent headline IDs: {recent_headline_ids}")
                    cur.execute("""
                        DELETE FROM quiz
                        WHERE created_at < %s
                        AND slide_id NOT IN (SELECT unnest(%s))
                        AND id NOT IN (SELECT quiz_id FROM scores WHERE quiz_id IS NOT NULL)
                        RETURNING id
                    """, (cleanup_time, recent_slide_ids))
                    deleted_quiz_ids = [row[0] for row in cur.fetchall()]
                    logging.debug(f"Deleted quiz records: {len(deleted_quiz_ids)} IDs: {deleted_quiz_ids}")
                    cur.execute("""
                        DELETE FROM slides
                        WHERE created_at < %s
                        AND id NOT IN (SELECT unnest(%s))
                        AND id NOT IN (SELECT slide_id FROM quiz WHERE slide_id IS NOT NULL)
                        RETURNING id
                    """, (cleanup_time, recent_slide_ids))
                    deleted_slide_ids = [row[0] for row in cur.fetchall()]
                    logging.debug(f"Deleted slide records: {len(deleted_slide_ids)} IDs: {deleted_slide_ids}")
                    cur.execute("""
                        DELETE FROM headlines
                        WHERE timestamp < %s
                        AND id NOT IN (SELECT unnest(%s))
                        AND id NOT IN (SELECT headline_id FROM slides WHERE headline_id IS NOT NULL)
                        RETURNING id
                    """, (cleanup_time, recent_headline_ids))
                    deleted_headline_ids = [row[0] for row in cur.fetchall()]
                    logging.debug(f"Deleted headline records: {len(deleted_headline_ids)} IDs: {deleted_headline_ids}")
                    cur.execute("""
                        DO $$  
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint
                                WHERE conname = 'slides_headline_id_fkey'
                                AND conrelid = 'slides'::regclass
                            ) THEN
                                ALTER TABLE slides ADD CONSTRAINT slides_headline_id_fkey
                                FOREIGN KEY (headline_id) REFERENCES headlines(id) ON DELETE SET NULL;
                            END IF;
                        END   $$;
                    """)
                    cur.execute("""
                        DO $$  
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint
                                WHERE conname = 'quiz_slide_id_fkey'
                                AND conrelid = 'quiz'::regclass
                            ) THEN
                                ALTER TABLE quiz ADD CONSTRAINT quiz_slide_id_fkey
                                FOREIGN KEY (slide_id) REFERENCES slides(id) ON DELETE SET NULL;
                            END IF;
                        END   $$;
                    """)
                    conn.commit()
                    logging.debug(f"Cleaned up data older than 1 day at {datetime.datetime.now(timezone.utc)}")
                except psycopg2.Error as e:
                    logging.error(f"Database error while cleaning up old data: {e}")
                    conn.rollback()
                logging.info(f"Refresh completed at {datetime.datetime.now(timezone.utc)}, total time {datetime.datetime.now(timezone.utc) - start_time}")
                return
        except Exception as e:
            logging.error(f"Refresh database failed on attempt {attempt + 1}/{max_attempts}: {str(e)}")
            if attempt < max_attempts - 1:
                time.sleep(5)
                continue
            logging.error(f"Refresh database failed after {max_attempts} attempts")
            return

@content_bp.route('/api/latest_refresh', methods=['GET'])
def get_latest_refresh():
    from datetime import timezone, timedelta
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(timestamp) FROM headlines")
            latest_timestamp = cur.fetchone()[0]
            if latest_timestamp:
                edt_timezone = timezone(timedelta(hours=-4))
                latest_timestamp_edt = latest_timestamp.astimezone(edt_timezone)
                formatted_time = latest_timestamp_edt.strftime('%b %d, %Y %I:%M %p EDT')
                return jsonify({"latest_refresh": formatted_time, "timestamp": latest_timestamp.timestamp()})
            else:
                logging.warning("No headlines found for latest refresh timestamp")
                return jsonify({"latest_refresh": "No refresh data", "timestamp": 0})
    except psycopg2.Error as e:
        logging.error(f"Database error fetching latest refresh: {e}")
        return jsonify({"error": "Database error"}), 500

@content_bp.route('/api/headlines', methods=['GET'])
def get_headlines():
    with get_db_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT title, description, link, source FROM headlines ORDER BY timestamp DESC LIMIT 5")
        headlines = [{"title": row[0], "description": row[1] or "No description", "link": row[2] or "#", "source": row[3]} for row in cur.fetchall()]
    logging.debug(f"Serving headlines: {headlines}")
    return jsonify(headlines)

@content_bp.route('/api/slides', methods=['GET'])
def get_slides():
    from psycopg2.extras import DictCursor
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

@content_bp.route('/api/quiz', methods=['GET'])
def get_quiz():
    from psycopg2.extras import DictCursor
    with get_db_conn() as conn:
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT id, question, options, correct, explanation
            FROM quiz
            ORDER BY created_at DESC
            LIMIT 5
        """)
        quiz = [{"id": row['id'], "question": row['question'], "options": json.loads(row['options']), "correct": row['correct'], "explanation": row['explanation']} for row in cur.fetchall()]
    logging.debug(f"Serving quiz: {quiz}")
    return jsonify(quiz)

def start_scheduler():
    logging.info("Starting scheduler for daily refresh and X post")
    from social import post_to_x
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