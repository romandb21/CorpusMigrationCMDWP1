import json
import random
import re
import time

import requests
from bs4 import BeautifulSoup
from joblib import Parallel, delayed
from loguru import logger

URL = (
    "https://www.vie-publique.fr/discours/recherche?"
    "search_api_fulltext_discours=&"
    "sort_by=field_date_prononciation_discour&"
    "field_intervenant_title=&"
    "field_intervenant_qualite=&"
    "field_date_prononciation_discour_interval%5Bmin%5D={}&"
    "field_date_prononciation_discour_interval%5Bmax%5D={}&"
    "page={}"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def gather_link_collection(
    output_file: str = None,
    n_jobs: int = 1,
    start_year: int = None,
    end_year: int = None,
):
    """
    Gather discours links from vie-publique.fr

    :param output_file: file where links will be written
    :type output_file: str

    :param n_jobs: number of parallel processes to use
    :type n_jobs: int

    :param start_year: first year to include in the scrapping
    :type start_year: int

    :param end_year: last year to include in the scrapping
    :type end_year: int

    :return: None
    """

    year_range = list(range(start_year, end_year + 1))

    page = requests.get(
        URL.format("{}-01-01".format(start_year), "{}-12-31".format(end_year), 0),
        headers=HEADERS
    )
    
    soup = BeautifulSoup(page.content, "html.parser")

    n_doc_for_interval = int(
        re.sub(
            r"\s",
            "",
            re.search(r"\d+(\s\d+)?", soup.find("h2", class_="vp-count-search").text).group(
                0
            ),
        )
    )
    logger.info("Total number of documents: {}".format(n_doc_for_interval))
    logger.info("Total number of years to fetch: {}".format(len(year_range)))
    random.shuffle(year_range)

    logger.info("Start link extraction with {} processes".format(n_jobs))
    results = Parallel(n_jobs=n_jobs)(
        delayed(extract_links_from_year)(year=year) for year in year_range
    )

    links = {}

    for year, page_links in results:
        links[year] = page_links

    logger.info("Total number of links: {}".format(len(links)))

    with open(output_file, "w", encoding="UTF-8") as output_file:
        json.dump(links, output_file, indent=2)


def extract_links_from_year(year: str = None):
    """
    Extract discours links from a specific year

    :param start_url: template URL to use for scrapping
    :type start_url: str

    :param year: year to consider for scrapping
    :type year: int

    :return: list of links
    :rtype: set
    """

    time.sleep(random.uniform(1, 3))  # Random delay between requests
    logger.info(f"Processing year {year}...")
    
    page = requests.get(
        URL.format("{}-01-01".format(year), "{}-12-31".format(year), 0),
        headers=HEADERS,
        timeout=30
    )
    soup = BeautifulSoup(page.content, "html.parser")
    n_doc_for_year = int(
        re.sub(
            r"\s",
            "",
            re.search(r"\d+(\s\d+)?", soup.find("h2", class_="vp-count-search").text).group(
                0
            ),
        )
    )

    links = list()

    logger.info(f"Year {year}: Fetching first semester...")
    first_semester = get_links(
        start_date="{}-01-01".format(year), end_date="{}-06-30".format(year)
    )
    logger.info(f"Year {year}: First semester done - {len(first_semester)} links")
    
    logger.info(f"Year {year}: Fetching second semester...")
    second_semester = get_links(
        start_date="{}-07-01".format(year), end_date="{}-12-31".format(year)
    )
    logger.info(f"Year {year}: Second semester done - {len(second_semester)} links")

    for url in first_semester:
        links.append(url)

    for url in second_semester:
        links.append(url)

    assert len(links) == n_doc_for_year

    return year, links


def get_links(start_date: str = None, end_date: str = None):

    logger.info(f"get_links: {start_date} to {end_date}")
    
    page = requests.get(
        URL.format(start_date, end_date, 0),
        headers=HEADERS,
        timeout=30
    )
    soup = BeautifulSoup(page.content, "html.parser")
    n_doc_for_interval = int(
        re.sub(
            r"\s",
            "",
            re.search(r"\d+(\s\d+)?", soup.find("h2", class_="vp-count-search").text).group(
                0
            ),
        )
    )

    n_pages = n_doc_for_interval // 10
    if n_doc_for_interval % 10 != 0:
        n_pages += 1

    logger.info(f"  {n_doc_for_interval} docs across {n_pages} pages")

    page_links = []
    pages = list(range(n_pages))

    while len(pages) > 0:

        p = pages.pop()
        
        if p % 10 == 0:  # Log every 10 pages
            logger.info(f"  Processing page {p}/{n_pages}...")

        time.sleep(random.uniform(0.5, 1.5))  # Small delay between pages
        
        try:
            page = requests.get(
                URL.format(start_date, end_date, p),
                headers=HEADERS,
                timeout=30
            )
        except Exception as e:
            logger.error(f"  Error on page {p}: {e}")
            pages.insert(0, p)
            time.sleep(5)
            continue
            
        soup = BeautifulSoup(page.content, "html.parser")

        # Fetch links - new HTML structure using DSFR
        articles = soup.find_all("div", class_="views-row")
        if len(articles) == 0:
            pages.insert(0, p)
            logger.warning(f"  No articles found on page {p}, retrying...")
            time.sleep(5)
            continue

        for div in articles:
            h3 = div.find("h3", class_="fr-card__title")
            if h3:
                a = h3.find("a")
                if a and a.get("href"):
                    page_links.append(a.get("href"))

    assert len(page_links) == n_doc_for_interval

    return page_links
