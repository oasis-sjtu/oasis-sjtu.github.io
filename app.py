from flask import Flask, Response, render_template, url_for
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


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html", page_title="Page not found"), 404


# GitHub Pages serves /404.html for unknown URLs; Frozen-Flask picks these routes up
# automatically because they take no arguments.
@app.route("/404.html")
def not_found_page():
    return render_template("404.html", page_title="Page not found")


@app.route("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\n\nSitemap: {config.SITE_URL}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    urls = [config.SITE_URL + url_for(endpoint) for endpoint in ("home", "people", "publication")]
    return Response(render_template("sitemap.xml", urls=urls), mimetype="application/xml")


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
