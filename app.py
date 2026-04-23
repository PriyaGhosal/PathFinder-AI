from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # MySQL is enabled when PyMySQL is installed and env vars are present.
    pymysql = None
    DictCursor = None

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "database" / "pathfinder.db"


def load_env_file() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key-for-production")


def load_json(filename: str):
    with (DATA_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


CAREERS = load_json("careers.json")
TRANSLATIONS = load_json("translations.json")
CAREER_BY_ID = {career["id"]: career for career in CAREERS}

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST"),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
}
USE_MYSQL = bool(pymysql and MYSQL_CONFIG["host"] and MYSQL_CONFIG["user"] and MYSQL_CONFIG["database"])


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def adapt_sql(sql: str) -> str:
    return sql.replace("?", "%s") if USE_MYSQL else sql


def get_db():
    if USE_MYSQL:
        return pymysql.connect(
            host=MYSQL_CONFIG["host"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            database=MYSQL_CONFIG["database"],
            port=MYSQL_CONFIG["port"],
            cursorclass=DictCursor,
            autocommit=True,
        )
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row)


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(adapt_sql(sql), params)
        rows = cursor.fetchall()
    return [row_to_dict(row) for row in rows]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(adapt_sql(sql), params)
        row = cursor.fetchone()
    return row_to_dict(row)


def execute(sql: str, params: tuple = ()) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(adapt_sql(sql), params)
        if not USE_MYSQL:
            conn.commit()
        return cursor.lastrowid or 0


def execute_many(sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.executemany(adapt_sql(sql), rows)
        if not USE_MYSQL:
            conn.commit()


def init_db() -> None:
    id_type = "INT AUTO_INCREMENT PRIMARY KEY" if USE_MYSQL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    statements = [
        f"""
        CREATE TABLE IF NOT EXISTS assessments (
            id {id_type},
            name TEXT NOT NULL,
            language TEXT NOT NULL,
            academic_stream TEXT NOT NULL,
            subjects TEXT NOT NULL,
            interests TEXT NOT NULL,
            skills TEXT NOT NULL,
            work_style TEXT NOT NULL,
            goal TEXT NOT NULL,
            recommendations TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id {id_type},
            name VARCHAR(120) NOT NULL,
            email VARCHAR(180) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            blocked INT NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS products (
            id {id_type},
            title VARCHAR(180) NOT NULL,
            slug VARCHAR(220) NOT NULL UNIQUE,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            category VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            popularity INT NOT NULL DEFAULT 0,
            file_path TEXT NOT NULL,
            screenshots_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS cart_items (
            id {id_type},
            user_id INT,
            session_id VARCHAR(120),
            product_id INT NOT NULL,
            quantity INT NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS orders (
            id {id_type},
            user_id INT NOT NULL,
            total REAL NOT NULL,
            discount REAL NOT NULL DEFAULT 0,
            tax REAL NOT NULL DEFAULT 0,
            status VARCHAR(40) NOT NULL,
            payment_method VARCHAR(80) NOT NULL,
            transaction_id VARCHAR(120) NOT NULL,
            coupon_code VARCHAR(80),
            created_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS order_items (
            id {id_type},
            order_id INT NOT NULL,
            product_id INT NOT NULL,
            price REAL NOT NULL,
            download_token VARCHAR(120) NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS coupons (
            id {id_type},
            code VARCHAR(80) NOT NULL UNIQUE,
            discount_type VARCHAR(20) NOT NULL,
            value REAL NOT NULL,
            expiry_date VARCHAR(20),
            usage_limit INT NOT NULL DEFAULT 100,
            used_count INT NOT NULL DEFAULT 0,
            active INT NOT NULL DEFAULT 1
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS faqs (
            id {id_type},
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            active INT NOT NULL DEFAULT 1
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS support_messages (
            id {id_type},
            name VARCHAR(120) NOT NULL,
            email VARCHAR(180) NOT NULL,
            message TEXT NOT NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS settings (
            setting_key VARCHAR(80) PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
        """,
    ]
    with get_db() as conn:
        cursor = conn.cursor()
        for statement in statements:
            cursor.execute(statement)
        if not USE_MYSQL:
            conn.commit()
    seed_defaults()


def seed_defaults() -> None:
    if not query_one("SELECT id FROM users WHERE role = ? LIMIT 1", ("admin",)):
        execute(
            """
            INSERT INTO users (name, email, password_hash, role, blocked, created_at)
            VALUES (?, ?, ?, 'admin', 0, ?)
            """,
            (
                os.getenv("ADMIN_NAME", "PathFinder Admin"),
                os.getenv("ADMIN_EMAIL", "admin@pathfinder.local"),
                generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123")),
                now_iso(),
            ),
        )

    if not query_one("SELECT id FROM products LIMIT 1"):
        products = [
            (
                "AI Career Roadmap Pack",
                "ai-career-roadmap-pack",
                "A premium PDF pack with 12-month AI, data science, and software career roadmaps.",
                499.0,
                "Roadmaps",
                "active",
                96,
                "downloads/ai-career-roadmap-pack.pdf",
                json.dumps(["Roadmap preview", "Skill timeline", "Project planner"]),
                now_iso(),
            ),
            (
                "Resume Template Bundle",
                "resume-template-bundle",
                "ATS-friendly resume templates for freshers, developers, analysts, and designers.",
                299.0,
                "Templates",
                "active",
                84,
                "downloads/resume-template-bundle.zip",
                json.dumps(["Resume preview", "Cover letter", "LinkedIn checklist"]),
                now_iso(),
            ),
            (
                "Interview Preparation Kit",
                "interview-preparation-kit",
                "Question banks, HR answers, technical practice sheets, and mock interview tracker.",
                399.0,
                "Interview",
                "active",
                91,
                "downloads/interview-preparation-kit.pdf",
                json.dumps(["Question bank", "Mock tracker", "Answer framework"]),
                now_iso(),
            ),
            (
                "Personal Assessment Report Pack",
                "personal-assessment-report-pack",
                "A downloadable guide to understand career match scores, skill gaps, and next steps.",
                199.0,
                "Reports",
                "active",
                73,
                "downloads/personal-assessment-report-pack.pdf",
                json.dumps(["Score guide", "Skill map", "Action checklist"]),
                now_iso(),
            ),
            (
                "Counselling Starter Bundle",
                "counselling-starter-bundle",
                "Career clarity worksheets, mentor question prompts, and decision-making templates.",
                599.0,
                "Counselling",
                "active",
                88,
                "downloads/counselling-starter-bundle.zip",
                json.dumps(["Worksheet", "Mentor prompts", "Decision matrix"]),
                now_iso(),
            ),
        ]
        execute_many(
            """
            INSERT INTO products (
                title, slug, description, price, category, status, popularity,
                file_path, screenshots_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            products,
        )

    if not query_one("SELECT id FROM coupons LIMIT 1"):
        execute(
            """
            INSERT INTO coupons (code, discount_type, value, expiry_date, usage_limit, used_count, active)
            VALUES ('CAREER10', 'percentage', 10, '', 100, 0, 1)
            """
        )

    if not query_one("SELECT id FROM faqs LIMIT 1"):
        execute_many(
            "INSERT INTO faqs (question, answer, active) VALUES (?, ?, 1)",
            [
                ("How do downloads work?", "After demo checkout, purchased resources appear in Orders and Downloads."),
                ("Is payment real?", "This project version uses demo checkout for college/project presentation."),
                ("Can I update career products?", "Admins can add, edit, activate, or deactivate products from the dashboard."),
            ],
        )

    defaults = {
        "currency": "INR",
        "tax_percent": "18",
        "brand_name": "PathFinder-AI",
        "footer_text": "Personalized career counselling and digital career resources.",
        "payment_gateway": "Demo Checkout",
    }
    for key, value in defaults.items():
        if not query_one("SELECT setting_key FROM settings WHERE setting_key = ?", (key,)):
            execute("INSERT INTO settings (setting_key, setting_value) VALUES (?, ?)", (key, value))


def selected_language() -> str:
    language = request.values.get("language") or session.get("language") or request.cookies.get("language") or "en"
    if language not in TRANSLATIONS:
        language = "en"
    session["language"] = language
    return language


def translate(key: str, language: str | None = None) -> str:
    lang = language or session.get("language") or request.cookies.get("language") or "en"
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))


@app.after_request
def persist_language_cookie(response):
    response.set_cookie("language", session.get("language", "en"), max_age=60 * 60 * 24 * 365)
    return response


def current_user() -> dict | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def cart_owner_filter() -> tuple[str, tuple]:
    user = current_user()
    if user:
        return "user_id = ?", (user["id"],)
    session.setdefault("cart_session_id", str(uuid4()))
    return "session_id = ?", (session["cart_session_id"],)


def get_settings() -> dict:
    return {row["setting_key"]: row["setting_value"] for row in query_all("SELECT * FROM settings")}


def parse_screenshots(product: dict) -> list[str]:
    try:
        return json.loads(product.get("screenshots_json") or "[]")
    except json.JSONDecodeError:
        return []


def money(value: float) -> str:
    settings = get_settings()
    currency = settings.get("currency", "INR")
    symbol = "₹" if currency.upper() == "INR" else currency.upper() + " "
    return f"{symbol}{float(value):.2f}"


def product_categories() -> list[str]:
    return [row["category"] for row in query_all("SELECT DISTINCT category FROM products ORDER BY category")]


def active_products(query: str = "", category: str = "", sort: str = "popular") -> list[dict]:
    sql = "SELECT * FROM products WHERE status = 'active'"
    params: list = []
    if query:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(category) LIKE ?)"
        like = f"%{query.lower()}%"
        params.extend([like, like, like])
    if category:
        sql += " AND category = ?"
        params.append(category)
    order = {
        "price_low": "price ASC",
        "price_high": "price DESC",
        "newest": "id DESC",
        "popular": "popularity DESC",
    }.get(sort, "popularity DESC")
    return query_all(f"{sql} ORDER BY {order}", tuple(params))


def cart_items() -> list[dict]:
    where, params = cart_owner_filter()
    rows = query_all(
        f"""
        SELECT cart_items.id AS cart_id, cart_items.quantity, products.*
        FROM cart_items
        JOIN products ON products.id = cart_items.product_id
        WHERE {where}
        ORDER BY cart_items.id DESC
        """,
        params,
    )
    for row in rows:
        row["line_total"] = float(row["price"]) * int(row["quantity"])
    return rows


def cart_total(items: list[dict]) -> float:
    return sum(float(item["line_total"]) for item in items)


def validate_coupon(code: str, subtotal: float) -> tuple[dict | None, float, str]:
    if not code:
        return None, 0.0, ""
    coupon = query_one("SELECT * FROM coupons WHERE UPPER(code) = UPPER(?) AND active = 1", (code.strip(),))
    if not coupon:
        return None, 0.0, "Invalid coupon code."
    if coupon["expiry_date"] and coupon["expiry_date"] < datetime.utcnow().date().isoformat():
        return None, 0.0, "Coupon has expired."
    if int(coupon["used_count"]) >= int(coupon["usage_limit"]):
        return None, 0.0, "Coupon usage limit reached."
    if coupon["discount_type"] == "percentage":
        discount = subtotal * (float(coupon["value"]) / 100)
    else:
        discount = float(coupon["value"])
    return coupon, min(discount, subtotal), ""


def parse_profile(form) -> dict:
    return {
        "name": form.get("name", "Student").strip() or "Student",
        "language": form.get("language", "en"),
        "academic_stream": form.get("academic_stream", "").strip(),
        "subjects": form.getlist("subjects"),
        "interests": form.getlist("interests"),
        "skills": form.getlist("skills"),
        "work_style": form.get("work_style", "").strip(),
        "goal": form.get("goal", "").strip(),
    }


def ensure_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def normalize_profile(data: dict) -> dict:
    return {
        "name": str(data.get("name") or "Student").strip() or "Student",
        "language": str(data.get("language") or "en"),
        "academic_stream": str(data.get("academic_stream") or "").strip(),
        "subjects": ensure_list(data.get("subjects")),
        "interests": ensure_list(data.get("interests")),
        "skills": ensure_list(data.get("skills")),
        "work_style": str(data.get("work_style") or "").strip(),
        "goal": str(data.get("goal") or "").strip(),
    }


def matches(user_values: list[str], career_values: list[str]) -> list[str]:
    return sorted(set(user_values).intersection(career_values))


def score_career(profile: dict, career: dict) -> dict:
    score = 0
    reasons = []
    if profile["academic_stream"] in career["preferred_streams"]:
        score += 22
        reasons.append("Your academic stream matches this career area.")
    subject_matches = matches(profile["subjects"], career["subjects"])
    if subject_matches:
        score += min(24, len(subject_matches) * 8)
        reasons.append(f"Strong subject fit: {', '.join(subject_matches)}.")
    interest_matches = matches(profile["interests"], career["interests"])
    if interest_matches:
        score += min(24, len(interest_matches) * 8)
        reasons.append(f"Your interests align with: {', '.join(interest_matches)}.")
    skill_matches = matches(profile["skills"], career["skills"])
    if skill_matches:
        score += min(22, len(skill_matches) * 6)
        reasons.append(f"Current skill match: {', '.join(skill_matches)}.")
    if profile["work_style"] in career["work_styles"]:
        score += 8
        reasons.append("Your preferred work style fits this career.")
    skill_gap = sorted(set(career["skills"]) - set(profile["skills"]))
    confidence = max(35, min(98, score))
    if not reasons:
        reasons.append("This is a growth option based on your broad preferences.")
    return {
        "id": career["id"],
        "title": career["title"],
        "category": career["category"],
        "description": career["description"],
        "confidence": confidence,
        "reasons": reasons,
        "matched_skills": skill_matches,
        "skill_gap": skill_gap[:6],
        "future_scope": career["future_scope"],
        "average_salary": career["average_salary"],
    }


def recommend_careers(profile: dict) -> list[dict]:
    recommendations = [score_career(profile, career) for career in CAREERS]
    recommendations.sort(key=lambda item: item["confidence"], reverse=True)
    return recommendations[:5]


def save_assessment(profile: dict, recommendations: list[dict]) -> None:
    execute(
        """
        INSERT INTO assessments (
            name, language, academic_stream, subjects, interests, skills,
            work_style, goal, recommendations, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile["name"],
            profile["language"],
            profile["academic_stream"],
            json.dumps(profile["subjects"]),
            json.dumps(profile["interests"]),
            json.dumps(profile["skills"]),
            profile["work_style"],
            profile["goal"],
            json.dumps(recommendations),
            now_iso(),
        ),
    )


def recent_assessments(limit: int = 6) -> list[dict]:
    rows = query_all(
        """
        SELECT name, academic_stream, recommendations, created_at
        FROM assessments
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    assessments = []
    for row in rows:
        recs = json.loads(row["recommendations"])
        assessments.append(
            {
                "name": row["name"],
                "academic_stream": row["academic_stream"],
                "top_career": recs[0]["title"] if recs else "Not available",
                "confidence": recs[0]["confidence"] if recs else 0,
                "created_at": row["created_at"],
            }
        )
    return assessments


def dashboard_metrics() -> dict:
    assessment_rows = query_all("SELECT recommendations FROM assessments ORDER BY id DESC")
    career_counts: dict[str, int] = {}
    confidences = []
    for row in assessment_rows:
        recommendations = json.loads(row["recommendations"])
        if not recommendations:
            continue
        top = recommendations[0]
        career_counts[top["title"]] = career_counts.get(top["title"], 0) + 1
        confidences.append(top["confidence"])
    top_careers = sorted(career_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    return {
        "total_assessments": len(assessment_rows),
        "average_confidence": round(sum(confidences) / len(confidences)) if confidences else 0,
        "unique_top_careers": len(career_counts),
        "top_careers": [{"title": title, "count": count} for title, count in top_careers],
    }


def career_for_comparison(career: dict, profile: dict | None = None) -> dict:
    profile = profile or {"skills": []}
    return {
        **career,
        "skill_gap": sorted(set(career["skills"]) - set(profile.get("skills", []))),
        "matched_skills": sorted(set(career["skills"]).intersection(profile.get("skills", []))),
    }


def build_report(profile: dict, recommendations: list[dict]) -> str:
    lines = [
        "PathFinder-AI Career Counselling Report",
        "=" * 42,
        f"Student: {profile.get('name', 'Student')}",
        f"Academic stream: {profile.get('academic_stream', 'Not provided')}",
        f"Goal: {profile.get('goal') or 'Not provided'}",
        "",
        "Top Recommendations",
        "-" * 19,
    ]
    for index, rec in enumerate(recommendations, start=1):
        lines.extend(
            [
                f"{index}. {rec['title']} ({rec['confidence']}% match)",
                f"   Category: {rec['category']}",
                f"   Why: {' '.join(rec['reasons'])}",
                f"   Skill gap: {', '.join(rec['skill_gap']) if rec['skill_gap'] else 'No major gap'}",
                f"   Future scope: {rec['future_scope']}",
                "",
            ]
        )
    return "\n".join(lines)


def assistant_reply(question: str, profile: dict | None, recommendations: list[dict] | None) -> str:
    if not profile or not recommendations:
        return "Start with the assessment first. After that I can explain matches, skill gaps, salaries, and roadmaps."
    top = recommendations[0]
    text = question.lower()
    if any(word in text for word in ["best", "top", "recommend"]):
        return f"Your strongest match is {top['title']} at {top['confidence']}%. Main reason: {top['reasons'][0]}"
    if any(word in text for word in ["skill", "gap", "learn", "roadmap"]):
        gap = ", ".join(top["skill_gap"]) if top["skill_gap"] else "no major missing core skills"
        return f"For {top['title']}, focus next on: {gap}. Open the roadmap page for beginner, intermediate, and advanced steps."
    if any(word in text for word in ["salary", "scope", "future"]):
        career = CAREER_BY_ID.get(top["id"])
        return f"{top['title']} has this scope: {top['future_scope']} Salary guide: {career['average_salary'] if career else top['average_salary']}"
    if any(word in text for word in ["compare", "confuse", "choose"]):
        names = ", ".join(item["title"] for item in recommendations[:3])
        return f"Compare these first: {names}. Choose the one where your confidence score and long-term interest are both strong."
    return f"Based on your profile, {top['title']} is the best current direction. Ask me about skills, salary, roadmap, or comparison for more detail."


@app.context_processor
def inject_helpers():
    return {
        "language": session.get("language", "en"),
        "languages": [{"code": "en", "label": "English"}, {"code": "hi", "label": "Hindi"}],
        "t": translate,
        "user": current_user(),
        "cart_count": len(cart_items()) if request.endpoint != "static" else 0,
        "money": money,
        "settings": get_settings(),
        "use_mysql": USE_MYSQL,
    }


@app.route("/")
def index():
    selected_language()
    return render_template("index.html", careers=CAREERS, featured_products=active_products(sort="popular")[:3])


@app.route("/about")
def about():
    selected_language()
    faqs = query_all("SELECT * FROM faqs WHERE active = 1 ORDER BY id DESC")
    return render_template("about.html", faqs=faqs)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    selected_language()
    sent = False
    if request.method == "POST":
        execute(
            "INSERT INTO support_messages (name, email, message, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (
                request.form.get("name", "").strip(),
                request.form.get("email", "").strip(),
                request.form.get("message", "").strip(),
                now_iso(),
            ),
        )
        sent = True
    return render_template("contact.html", sent=sent)


@app.route("/ai-chat")
def ai_chat():
    return redirect(url_for("assistant"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    selected_language()
    error = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if query_one("SELECT id FROM users WHERE email = ?", (email,)):
            error = "Email already registered."
        elif not name or not email or len(password) < 6:
            error = "Enter a name, email, and password with at least 6 characters."
        else:
            user_id = execute(
                "INSERT INTO users (name, email, password_hash, role, blocked, created_at) VALUES (?, ?, ?, 'user', 0, ?)",
                (name, email, generate_password_hash(password), now_iso()),
            )
            session["user_id"] = user_id
            return redirect(url_for("profile"))
    return render_template("auth.html", mode="signup", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    selected_language()
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query_one("SELECT * FROM users WHERE email = ?", (email,))
        if not user or not check_password_hash(user["password_hash"], password):
            error = "Invalid email or password."
        elif int(user["blocked"]):
            error = "This account is blocked."
        else:
            session["user_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("profile"))
    return render_template("auth.html", mode="login", error=error)


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    selected_language()
    user = current_user()
    notice = ""
    error = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        if not name:
            error = "Name is required."
        else:
            execute("UPDATE users SET name = ? WHERE id = ?", (name, user["id"]))
            if password:
                if len(password) < 6:
                    error = "Password must be at least 6 characters."
                else:
                    execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), user["id"]))
                    notice = "Profile and password updated."
            else:
                notice = "Profile updated."
    return render_template("profile.html", notice=notice, error=error, orders=user_orders(user["id"]))


@app.route("/products")
def products():
    selected_language()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "popular")
    return render_template(
        "products.html",
        products=active_products(query, category, sort),
        categories=product_categories(),
        query=query,
        selected_category=category,
        sort=sort,
    )


@app.route("/products/<slug>")
def product_detail(slug: str):
    selected_language()
    product = query_one("SELECT * FROM products WHERE slug = ? AND status = 'active'", (slug,))
    if not product:
        return redirect(url_for("products"))
    related = query_all(
        "SELECT * FROM products WHERE category = ? AND slug != ? AND status = 'active' ORDER BY popularity DESC LIMIT 3",
        (product["category"], slug),
    )
    return render_template("product_detail.html", product=product, screenshots=parse_screenshots(product), related=related)


@app.route("/cart")
def cart():
    selected_language()
    items = cart_items()
    subtotal = cart_total(items)
    code = session.get("coupon_code", "")
    coupon, discount, coupon_error = validate_coupon(code, subtotal)
    settings = get_settings()
    tax = max(0, subtotal - discount) * (float(settings.get("tax_percent", 0)) / 100)
    total = max(0, subtotal - discount + tax)
    return render_template(
        "cart.html",
        items=items,
        subtotal=subtotal,
        coupon=coupon,
        discount=discount,
        tax=tax,
        total=total,
        coupon_error=coupon_error,
    )


@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id: int):
    product = query_one("SELECT id FROM products WHERE id = ? AND status = 'active'", (product_id,))
    if product:
        where, params = cart_owner_filter()
        existing = query_one(f"SELECT id, quantity FROM cart_items WHERE {where} AND product_id = ?", (*params, product_id))
        if existing:
            execute("UPDATE cart_items SET quantity = quantity + 1 WHERE id = ?", (existing["id"],))
        else:
            user = current_user()
            execute(
                "INSERT INTO cart_items (user_id, session_id, product_id, quantity, created_at) VALUES (?, ?, ?, 1, ?)",
                (user["id"] if user else None, session.get("cart_session_id"), product_id, now_iso()),
            )
    return redirect(request.referrer or url_for("cart"))


@app.route("/cart/update/<int:cart_id>", methods=["POST"])
def update_cart(cart_id: int):
    quantity = max(0, int(request.form.get("quantity", 1)))
    if quantity == 0:
        execute("DELETE FROM cart_items WHERE id = ?", (cart_id,))
    else:
        execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (quantity, cart_id))
    return redirect(url_for("cart"))


@app.route("/cart/coupon", methods=["POST"])
def apply_coupon():
    session["coupon_code"] = request.form.get("coupon_code", "").strip()
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    selected_language()
    items = cart_items()
    if not items:
        return redirect(url_for("products"))
    subtotal = cart_total(items)
    coupon, discount, coupon_error = validate_coupon(session.get("coupon_code", ""), subtotal)
    settings = get_settings()
    tax = max(0, subtotal - discount) * (float(settings.get("tax_percent", 0)) / 100)
    total = max(0, subtotal - discount + tax)
    if request.method == "POST":
        transaction_id = f"DEMO-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
        order_id = execute(
            """
            INSERT INTO orders (user_id, total, discount, tax, status, payment_method, transaction_id, coupon_code, created_at)
            VALUES (?, ?, ?, ?, 'paid', ?, ?, ?, ?)
            """,
            (
                current_user()["id"],
                total,
                discount,
                tax,
                settings.get("payment_gateway", "Demo Checkout"),
                transaction_id,
                coupon["code"] if coupon else "",
                now_iso(),
            ),
        )
        for item in items:
            execute(
                "INSERT INTO order_items (order_id, product_id, price, download_token) VALUES (?, ?, ?, ?)",
                (order_id, item["id"], item["price"], secrets.token_urlsafe(18)),
            )
        if coupon:
            execute("UPDATE coupons SET used_count = used_count + 1 WHERE id = ?", (coupon["id"],))
        where, params = cart_owner_filter()
        execute(f"DELETE FROM cart_items WHERE {where}", params)
        session.pop("coupon_code", None)
        return redirect(url_for("order_detail", order_id=order_id))
    return render_template(
        "checkout.html",
        items=items,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=total,
        coupon_error=coupon_error,
    )


def user_orders(user_id: int) -> list[dict]:
    return query_all("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,))


@app.route("/orders")
@login_required
def orders():
    selected_language()
    return render_template("orders.html", orders=user_orders(current_user()["id"]))


@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id: int):
    selected_language()
    order = query_one("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, current_user()["id"]))
    if not order:
        return redirect(url_for("orders"))
    items = query_all(
        """
        SELECT order_items.*, products.title, products.file_path
        FROM order_items
        JOIN products ON products.id = order_items.product_id
        WHERE order_items.order_id = ?
        """,
        (order_id,),
    )
    return render_template("order_detail.html", order=order, items=items)


@app.route("/orders/<int:order_id>/invoice")
@login_required
def invoice(order_id: int):
    order = query_one("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, current_user()["id"]))
    if not order:
        return redirect(url_for("orders"))
    items = query_all(
        """
        SELECT products.title, order_items.price
        FROM order_items
        JOIN products ON products.id = order_items.product_id
        WHERE order_items.order_id = ?
        """,
        (order_id,),
    )
    lines = [
        "PathFinder-AI Invoice",
        f"Order #{order['id']}",
        f"Transaction: {order['transaction_id']}",
        f"Date: {order['created_at']}",
        "",
    ]
    for item in items:
        lines.append(f"- {item['title']}: {money(item['price'])}")
    lines.extend(["", f"Discount: {money(order['discount'])}", f"Tax: {money(order['tax'])}", f"Total: {money(order['total'])}"])
    return Response("\n".join(lines), mimetype="text/plain", headers={"Content-Disposition": f"attachment; filename=invoice-{order_id}.txt"})


@app.route("/downloads")
@login_required
def downloads():
    selected_language()
    items = query_all(
        """
        SELECT order_items.*, products.title, products.file_path, orders.created_at
        FROM order_items
        JOIN products ON products.id = order_items.product_id
        JOIN orders ON orders.id = order_items.order_id
        WHERE orders.user_id = ?
        ORDER BY orders.id DESC
        """,
        (current_user()["id"],),
    )
    return render_template("downloads.html", items=items)


@app.route("/download/<token>")
@login_required
def download_file(token: str):
    item = query_one(
        """
        SELECT order_items.*, products.title, products.file_path, orders.user_id
        FROM order_items
        JOIN products ON products.id = order_items.product_id
        JOIN orders ON orders.id = order_items.order_id
        WHERE order_items.download_token = ?
        """,
        (token,),
    )
    if not item or item["user_id"] != current_user()["id"]:
        return redirect(url_for("downloads"))
    content = f"Demo secure download for {item['title']}\nFile path placeholder: {item['file_path']}\n"
    return Response(content, mimetype="text/plain", headers={"Content-Disposition": f"attachment; filename={item['title'].replace(' ', '-')}.txt"})


@app.route("/admin")
@admin_required
def admin():
    selected_language()
    stats = {
        "orders": query_one("SELECT COUNT(*) AS count FROM orders")["count"],
        "users": query_one("SELECT COUNT(*) AS count FROM users")["count"],
        "products": query_one("SELECT COUNT(*) AS count FROM products")["count"],
        "revenue": query_one("SELECT COALESCE(SUM(total), 0) AS total FROM orders")["total"],
    }
    top_products = query_all(
        """
        SELECT products.title, COUNT(order_items.id) AS sold
        FROM products
        LEFT JOIN order_items ON order_items.product_id = products.id
        GROUP BY products.id, products.title
        ORDER BY sold DESC
        LIMIT 5
        """
    )
    return render_template("admin_dashboard.html", stats=stats, top_products=top_products)


@app.route("/admin/products", methods=["GET", "POST"])
@admin_required
def admin_products():
    if request.method == "POST":
        product_id = request.form.get("id")
        title = request.form.get("title", "").strip()
        slug = request.form.get("slug", "").strip() or title.lower().replace(" ", "-")
        data = (
            title,
            slug,
            request.form.get("description", "").strip(),
            float(request.form.get("price", 0)),
            request.form.get("category", "").strip(),
            request.form.get("status", "active"),
            int(request.form.get("popularity", 0)),
            request.form.get("file_path", "").strip(),
            json.dumps([item.strip() for item in request.form.get("screenshots", "").split(",") if item.strip()]),
        )
        if product_id:
            execute(
                """
                UPDATE products
                SET title=?, slug=?, description=?, price=?, category=?, status=?, popularity=?, file_path=?, screenshots_json=?
                WHERE id=?
                """,
                (*data, product_id),
            )
        else:
            execute(
                """
                INSERT INTO products (title, slug, description, price, category, status, popularity, file_path, screenshots_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*data, now_iso()),
            )
        return redirect(url_for("admin_products"))
    product_id = request.args.get("edit")
    editing = query_one("SELECT * FROM products WHERE id = ?", (product_id,)) if product_id else None
    return render_template("admin_products.html", products=query_all("SELECT * FROM products ORDER BY id DESC"), editing=editing)


@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def admin_delete_product(product_id: int):
    execute("DELETE FROM products WHERE id = ?", (product_id,))
    return redirect(url_for("admin_products"))


@app.route("/admin/coupons", methods=["GET", "POST"])
@admin_required
def admin_coupons():
    if request.method == "POST":
        coupon_id = request.form.get("id")
        data = (
            request.form.get("code", "").strip().upper(),
            request.form.get("discount_type", "percentage"),
            float(request.form.get("value", 0)),
            request.form.get("expiry_date", ""),
            int(request.form.get("usage_limit", 100)),
            1 if request.form.get("active") == "on" else 0,
        )
        if coupon_id:
            execute("UPDATE coupons SET code=?, discount_type=?, value=?, expiry_date=?, usage_limit=?, active=? WHERE id=?", (*data, coupon_id))
        else:
            execute("INSERT INTO coupons (code, discount_type, value, expiry_date, usage_limit, used_count, active) VALUES (?, ?, ?, ?, ?, 0, ?)", data)
        return redirect(url_for("admin_coupons"))
    editing = query_one("SELECT * FROM coupons WHERE id = ?", (request.args.get("edit"),)) if request.args.get("edit") else None
    return render_template("admin_coupons.html", coupons=query_all("SELECT * FROM coupons ORDER BY id DESC"), editing=editing)


@app.route("/admin/faqs", methods=["GET", "POST"])
@admin_required
def admin_faqs():
    if request.method == "POST":
        faq_id = request.form.get("id")
        data = (request.form.get("question", ""), request.form.get("answer", ""), 1 if request.form.get("active") == "on" else 0)
        if faq_id:
            execute("UPDATE faqs SET question=?, answer=?, active=? WHERE id=?", (*data, faq_id))
        else:
            execute("INSERT INTO faqs (question, answer, active) VALUES (?, ?, ?)", data)
        return redirect(url_for("admin_faqs"))
    editing = query_one("SELECT * FROM faqs WHERE id = ?", (request.args.get("edit"),)) if request.args.get("edit") else None
    return render_template("admin_faqs.html", faqs=query_all("SELECT * FROM faqs ORDER BY id DESC"), editing=editing)


@app.route("/admin/orders")
@admin_required
def admin_orders():
    return render_template("admin_orders.html", orders=query_all("SELECT orders.*, users.name, users.email FROM orders JOIN users ON users.id = orders.user_id ORDER BY orders.id DESC"))


@app.route("/admin/users")
@admin_required
def admin_users():
    return render_template("admin_users.html", users=query_all("SELECT * FROM users ORDER BY id DESC"))


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(user_id: int):
    user = query_one("SELECT blocked, role FROM users WHERE id = ?", (user_id,))
    if user and user["role"] != "admin":
        execute("UPDATE users SET blocked = ? WHERE id = ?", (0 if int(user["blocked"]) else 1, user_id))
    return redirect(url_for("admin_users"))


@app.route("/admin/messages", methods=["GET", "POST"])
@admin_required
def admin_messages():
    if request.method == "POST":
        execute("UPDATE support_messages SET status = ? WHERE id = ?", (request.form.get("status", "open"), request.form.get("id")))
        return redirect(url_for("admin_messages"))
    return render_template("admin_messages.html", messages=query_all("SELECT * FROM support_messages ORDER BY id DESC"))


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        for key in ["currency", "tax_percent", "brand_name", "footer_text", "payment_gateway"]:
            execute("UPDATE settings SET setting_value = ? WHERE setting_key = ?", (request.form.get(key, ""), key))
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html", app_settings=get_settings())


@app.route("/assessment")
def assessment():
    selected_language()
    options = load_json("assessment_options.json")
    return render_template("assessment.html", options=options)


@app.route("/careers")
def careers():
    selected_language()
    query = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip()
    categories = sorted({career["category"] for career in CAREERS})
    careers_list = CAREERS
    if category:
        careers_list = [career for career in careers_list if career["category"] == category]
    if query:
        careers_list = [
            career
            for career in careers_list
            if query in career["title"].lower()
            or query in career["description"].lower()
            or query in " ".join(career["skills"]).lower()
        ]
    return render_template("careers.html", careers=careers_list, categories=categories, selected_category=category, query=query)


@app.route("/recommend", methods=["POST"])
def recommend():
    profile = parse_profile(request.form)
    session["language"] = profile["language"]
    recommendations = recommend_careers(profile)
    save_assessment(profile, recommendations)
    session["profile"] = profile
    session["recommendations"] = recommendations
    return redirect(url_for("results"))


@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    payload = request.get_json(silent=True) or {}
    profile = normalize_profile(payload)
    recommendations = recommend_careers(profile)
    return jsonify({"profile": profile, "recommendations": recommendations})


@app.route("/results")
def results():
    selected_language()
    recommendations = session.get("recommendations")
    profile = session.get("profile")
    if not recommendations or not profile:
        return redirect(url_for("assessment"))
    return render_template("results.html", profile=profile, recommendations=recommendations)


@app.route("/compare")
def compare():
    selected_language()
    profile = session.get("profile", {"skills": []})
    selected_ids = request.args.getlist("career_ids")
    if not selected_ids:
        selected_ids = [item["id"] for item in session.get("recommendations", [])[:3]]
    if not selected_ids:
        selected_ids = [career["id"] for career in CAREERS[:3]]
    selected_careers = [
        career_for_comparison(CAREER_BY_ID[career_id], profile)
        for career_id in selected_ids
        if career_id in CAREER_BY_ID
    ][:4]
    return render_template("compare.html", careers=CAREERS, selected_careers=selected_careers, selected_ids=selected_ids)


@app.route("/report")
def report():
    selected_language()
    recommendations = session.get("recommendations")
    profile = session.get("profile")
    if not recommendations or not profile:
        return redirect(url_for("assessment"))
    return render_template("report.html", profile=profile, recommendations=recommendations)


@app.route("/report/download")
def download_report():
    recommendations = session.get("recommendations")
    profile = session.get("profile")
    if not recommendations or not profile:
        return redirect(url_for("assessment"))
    filename = f"pathfinder-report-{profile.get('name', 'student').replace(' ', '-').lower()}.txt"
    return Response(build_report(profile, recommendations), mimetype="text/plain", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/assistant", methods=["GET", "POST"])
def assistant():
    selected_language()
    history = session.get("assistant_history", [])
    profile = session.get("profile")
    recommendations = session.get("recommendations")
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            history.append({"question": question, "answer": assistant_reply(question, profile, recommendations)})
            session["assistant_history"] = history[-8:]
        return redirect(url_for("assistant"))
    return render_template("assistant.html", history=history, profile=profile, recommendations=recommendations)


@app.route("/roadmap/<career_id>")
def roadmap(career_id: str):
    selected_language()
    career = CAREER_BY_ID.get(career_id)
    if not career:
        return redirect(url_for("results"))
    profile = session.get("profile", {"skills": []})
    skill_gap = sorted(set(career["skills"]) - set(profile.get("skills", [])))
    return render_template("roadmap.html", career=career, skill_gap=skill_gap)


@app.route("/dashboard")
def dashboard():
    selected_language()
    return render_template("dashboard.html", assessments=recent_assessments(8), metrics=dashboard_metrics())


@app.route("/set-language", methods=["GET", "POST"])
def set_language():
    language = request.form.get("language", "en")
    if request.method == "GET":
        language = request.args.get("language", language)
    if language in TRANSLATIONS:
        session["language"] = language
        session.modified = True
    return redirect(request.referrer or url_for("index"))


init_db()


if __name__ == "__main__":
    app.run(debug=True)
