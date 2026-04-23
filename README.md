# PathFinder-AI

AI powered career counselling platform built with Flask, HTML, CSS, JavaScript, Python, and an optional TensorFlow training pipeline.

## Features

- Student assessment form
- Personalized career recommendations
- Explainable match reasons
- Skill gap analysis
- Adaptive learning roadmaps
- English and Hindi UI labels
- Dark and light mode
- User signup, login, profile, orders, and downloads
- Career resource marketplace with product listing, detail, cart, coupons, demo checkout, invoices, and secure download placeholders
- Admin dashboard for products, users, orders, coupons, FAQs, support messages, settings, and analytics
- MySQL support through PyMySQL with local SQLite fallback for demo runs
- SQLite assessment history dashboard
- Career library with search and category filtering
- Career comparison page
- Printable and downloadable counselling report
- Rule-based career assistant chatbot
- Dashboard analytics for recommendation trends
- JSON API endpoint for recommendations
- Optional TensorFlow trainer in `model/train_model.py`

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

Default admin login after first run:

```text
Email: admin@pathfinder.local
Password: admin123
```

## MySQL Setup

Create a MySQL database, copy `.env.example` to `.env`, and update the values:

```text
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=pathfinder_ai
MYSQL_PORT=3306
```

When these values are present and `PyMySQL` is installed, the app uses MySQL. If MySQL is not configured, it falls back to the local SQLite demo database.

## Key Pages

```text
/assessment       Student career assessment
/results          Personalized recommendations
/careers          Searchable career library
/compare          Compare selected career paths
/assistant        Career counselling assistant
/report           Printable career report
/dashboard        Assessment history and analytics
/products         Career resource marketplace
/cart             Shopping cart
/checkout         Demo checkout
/orders           User order history
/downloads        Purchased resources
/admin            Admin dashboard
/api/recommend    JSON API for recommendations
```

## Train Optional TensorFlow Model

```bash
python model/train_model.py
```

The sample dataset is in `data/career_training_data.csv`. Replace it with a larger dataset for better model quality.

## Project Structure

```text
PathFinder-AI/
├── app.py
├── data/
│   ├── assessment_options.json
│   ├── career_training_data.csv
│   ├── careers.json
│   └── translations.json
├── model/
│   └── train_model.py
├── static/
│   ├── css/style.css
│   └── js/app.js
├── templates/
│   ├── assessment.html
│   ├── base.html
│   ├── dashboard.html
│   ├── index.html
│   ├── results.html
│   └── roadmap.html
└── requirements.txt
```
