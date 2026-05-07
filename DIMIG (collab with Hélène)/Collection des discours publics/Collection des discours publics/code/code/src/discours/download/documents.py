import json
import os
import time
from collections import defaultdict

import requests
from joblib import Parallel, delayed
from loguru import logger
from requests.exceptions import TooManyRedirects, ConnectionError, SSLError

URL = "https://www.vie-publique.fr{}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}


def get_documents(
    link_file: str = None,
    output_dir: str = None,
    n_jobs: int = 1,
    timestamp: str = None,
):

    logger.info("Load link list")
    with open(link_file, "r", encoding="UTF-8") as input_file:
        payload = json.load(input_file)

    logger.info("Remove duplicates")
    payload = {k: list(set(v)) for k, v in payload.items()}

    logger.info("Create directory")
    for year in payload:
        year_dir = os.path.join(output_dir, "{}".format(year))
        if not os.path.isdir(year_dir):
            os.makedirs(year_dir)

    logger.info("Fetch documents")
    results = Parallel(n_jobs=n_jobs)(
        delayed(download_year_documents)(
            target_directory=os.path.join(output_dir, "{}".format(year)),
            links=year_docs,
        )
        for year, year_docs in payload.items()
    )

    fetched = 0
    errors = defaultdict(list)

    for year_fetched, year_errors, year in results:
        fetched += year_fetched
        errors[year].extend(year_errors)

    error_file = os.path.join(output_dir, "errors-{}.json".format(timestamp))
    with open(error_file, "w", encoding="UTF-8") as output_file:
        json.dump(errors, output_file, indent=2)

    logger.info("Number of fetched documents: {}".format(fetched))
    logger.info("Number of errors: {}".format(sum([len(v) for k, v in errors.items()])))


def download_year_documents(target_directory: str = None, links: list = None):

    error_counter = 0
    year_fetched = 0
    year_errors = []

    while len(links) > 0:
        doc_url = links.pop(0)

        # Extract ID from URL (just the numeric part at the beginning)
        doc_slug = doc_url.split('/')[-1].split('?')[0]  # Get slug
        doc_id = doc_slug.split('-')[0]  # Get numeric ID before first dash
        
        target_file = os.path.join(
            target_directory, "{}.txt".format(doc_id)
        )
        if os.path.isfile(target_file):
            continue

        try:
            time.sleep(2)  # Delay between requests to avoid overwhelming server
            page = requests.get(URL.format(doc_url), headers=HEADERS, timeout=30)
        except (TooManyRedirects, ConnectionError, SSLError) as e:
            logger.warning(f"Connection error on {doc_id}: {e}")
            year_errors.append(doc_url)
            error_counter = 0
            time.sleep(10)  # Wait longer before next attempt
            continue
        except Exception as e:
            logger.error(f"Unexpected error on {doc_id}: {e}")
            year_errors.append(doc_url)
            continue

        status_code = page.status_code

        if status_code != 200:
            if error_counter >= 5:  # Reduced from 10
                year_errors.append(doc_url)
                error_counter = 0
                time.sleep(10)
                continue

            links.insert(0, doc_url)
            error_counter += 1
            time.sleep(5)
            continue

        error_counter = 0

        try:
            with open(target_file, "w", encoding="UTF-8") as output_file:
                output_file.write(page.text)
            year_fetched += 1
        except Exception as e:
            logger.error(f"Failed to write file {target_file}: {e}")
            year_errors.append(doc_url)

    return year_fetched, year_errors, os.path.basename(target_directory)
