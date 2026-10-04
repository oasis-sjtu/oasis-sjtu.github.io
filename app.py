from flask import Flask, render_template
from flask_bootstrap import Bootstrap5

import config
from data_utils import (
    load_awards,
    load_news,
    load_people_with_publications,
    load_publications,
    load_research,
    load_sponsors,
)

app = Flask(__name__)
# Serve Bootstrap from the Bootstrap-Flask package instead of a public CDN.
app.config["BOOTSTRAP_SERVE_LOCAL"] = True
# The package also ships Bootswatch themes, Sass sources, source maps and unused
# helpers; keep them out of the frozen site (they add ~15 MB).
app.config["FREEZER_STATIC_IGNORE"] = ["bootswatch", "umd", "icons", "*.map", "*.scss", "bootstrap.css"]
bootstrap = Bootstrap5(app)


@app.context_processor
def inject_site_metadata():
    return {
        "site_title": config.SITE_TITLE,
        "site_description": config.SITE_DESCRIPTION,
        "navbar_title": config.NAVBAR_TITLE,
        "copyright_year": config.COPYRIGHT_YEAR,
        "copyright_text": config.COPYRIGHT_TEXT,
        "site_url": config.SITE_URL,
        "pi_email_display": config.PI_EMAIL_DISPLAY,
    }


@app.route("/")
def home():
    return render_template(
        "index.html",
        page_title="Home",
        research_areas=load_research(),
        awards=load_awards(),
        news_items=load_news(limit=12),
        sponsors=load_sponsors(),
    )


@app.route("/people/")
def people():
    return render_template(
        "people.html",
        people=load_people_with_publications(),
        page_title="People",
    )


@app.route("/publication/")
def publication():
    return render_template(
        "publication.html",
        publications=load_publications(),
        page_title="Publications",
    )


if __name__ == "__main__":
    app.run(debug=config.DEBUG, host=config.HOST, port=config.PORT)
