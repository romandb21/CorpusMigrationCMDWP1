import json
import os
import random

import pendulum
from bs4 import BeautifulSoup
from joblib import Parallel, delayed
from loguru import logger
from lxml import html


def process_directory(
    input_dir: str = None, output_file: str = None, n_jobs: int = None
):

    to_be_processed = list()

    for year_dir in os.listdir(input_dir):
        if not os.path.isdir(os.path.join(input_dir, year_dir)):
            continue

        for filename in os.listdir(os.path.join(input_dir, year_dir)):
            source_filename = os.path.join(input_dir, year_dir, filename)
            to_be_processed.append((year_dir, source_filename))

    random.shuffle(to_be_processed)

    logger.info(
        "Processing {} with {} parallel processes".format(len(to_be_processed), n_jobs)
    )
    corpus = Parallel(n_jobs=n_jobs)(
        delayed(extract_data)(year=year, input_html_file=input_html_file)
        for year, input_html_file in to_be_processed
    )

    with open(output_file, "w", encoding="UTF-8") as output_file:
        json.dump(corpus, output_file, indent=2)


def extract_data(year: str = None, input_html_file: str = None):

    with open(input_html_file, "r", encoding="UTF-8") as input_file:
        content = input_file.read()

    soup = BeautifulSoup(content, "html.parser")
    metadata = extract_metadata(soup=soup)

    html_page = html.fromstring(content)
    span = html_page.find_class("field--name-field-texte-integral")

    if len(span) == 0:
        text = ""
    elif len(span) > 1:
        raise Exception
    else:
        text = span[0].text_content()

    payload = {"text": text, "metadata": metadata, "year": year}

    return payload


def extract_metadata(soup: BeautifulSoup = None):

    # INTERVENANTS
    # ===============================================================
    intervenants = []

    intervenants_ul = soup.find("ul", class_="line-intervenant")
    if intervenants_ul is not None:
        for li in intervenants_ul.find_all("li"):
            intervenant_position = ""
            intervenant_uid = ""
            intervenant_str = ""

            for e in li.children:
                if isinstance(e, str):
                    intervenant_position += e.strip("\n- ")
                elif e.name == "a":
                    intervenant_uid = li.find("a").get("href")
                    intervenant_str = li.find("a").text.strip("\n ")

            intervenants.append(
                {
                    "uid": intervenant_uid,
                    "str": intervenant_str,
                    "pos": intervenant_position,
                }
            )

    # CIRCONSTANCE
    # ===============================================================
    circonstance = ""
    circonstance_span = soup.find("span", class_="field--name-field-circonstance")

    if circonstance_span is not None:
        circonstance = circonstance_span.text.strip("\n ")

    # TAGS PRIMARY (nouvelle structure)
    # ===============================================================
    tags_primary = []
    # Nouvelle structure
    thematic_div = soup.find("div", class_="vp-page-thematic")
    if thematic_div is not None:
        for tag in thematic_div.find_all("a", class_="fr-tag"):
            tags_primary.append(tag.text.strip("\n "))
    
    # Fallback ancienne structure
    if not tags_primary:
        tags_div = soup.find("div", class_="thematicBox")
        if tags_div is not None:
            tags_ul = tags_div.find("ul", class_="tags--list")
            if tags_ul is not None:
                for li in tags_ul.find_all("li"):
                    a = li.find("a")
                    if a:
                        tags_primary.append(a.text.strip("\n "))

    # TAGS SECONDARY (nouvelle structure)
    # ===============================================================
    tags_secondary = []
    # Nouvelle structure
    tags_div = soup.find("div", class_="vp-tags")
    if tags_div is not None:
        for tag in tags_div.find_all("a", class_="fr-tag"):
            tags_secondary.append(tag.text.strip("\n "))
    
    # Fallback ancienne structure
    if not tags_secondary:
        tags_div = soup.find("div", class_="tagsBox")
        if tags_div is not None:
            tags_ul = tags_div.find("ul", {"class": ["tags--list", "list-secondaire"]})
            if tags_ul is not None:
                for li in tags_ul.find_all("li"):
                    a = li.find("a")
                    if a:
                        tags_secondary.append(a.text.strip("\n "))

    # TITLE (nouvelle structure en priorité)
    # ===============================================================
    title = ""
    # Nouvelle structure
    title_h1 = soup.find("h1", class_="fr-h3")
    if title_h1 is not None:
        title = title_h1.text.strip("\n ")
    
    # Fallback ancienne structure
    if not title:
        main_div = soup.find("div", role="article")
        if main_div is not None:
            title_h1 = main_div.find("h1")
            if title_h1 is not None:
                title = title_h1.text.strip("\n ")

    # URL (nouvelle structure avec link canonical)
    # ===============================================================
    url = ""
    # Nouvelle structure
    canonical = soup.find("link", rel="canonical")
    if canonical is not None:
        url = canonical.get("href", "")
    
    # Fallback ancienne structure
    if not url:
        main_div = soup.find("div", role="article")
        if main_div is not None:
            url = main_div.get("about", "")

    # DATE
    # ===============================================================
    date = ""
    # Nouvelle structure
    date_time = soup.find("time", class_="datetime")
    if date_time is not None:
        date = date_time.get("datetime", "")
    
    # Fallback ancienne structure
    if not date:
        date_span = soup.find("span", class_="field--name-field-date-prononciation-discour")
        if date_span is not None:
            date_span = date_span.text.strip("\n ")
            try:
                date = str(
                    pendulum.from_format(
                        date_span, "D MMMM YYYY", locale="fr", tz="Europe/Paris"
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to parse date '{date_span}': {e}")
                date = ""

    # ASSEMBLE AND RETURN
    # ===============================================================
    metadata = {
        "intervenants": intervenants,
        "circonstance": circonstance,
        "tags_primary": tags_primary,
        "tags_secondary": tags_secondary,
        "title": title,
        "date": date,
        "url": url,
    }

    return metadata
