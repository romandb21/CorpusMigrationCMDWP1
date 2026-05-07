import logging
import multiprocessing
import os
import sys
import time
from datetime import datetime, timedelta

import click
from loguru import logger

from .download.documents import get_documents
from .download.links import gather_link_collection
from .parsing.extract import process_directory


def time_decorator(func):
    def wrapper(*args, **kwargs):
        start_time = datetime.now()
        logger.info(
            "Process started on {}".format(start_time.strftime("%Y/%m/%d %H:%M:%S"))
        )
        func(*args, **kwargs)

        end_time = datetime.now()
        logger.info(
            "Process ended on {}".format(end_time.strftime("%Y/%m/%d %H:%M:%S"))
        )

        logger.info(
            "Elapsed Time: {}".format(
                timedelta(
                    seconds=round(
                        time.mktime(end_time.timetuple())
                        - time.mktime(start_time.timetuple())
                    )
                )
            )
        )

    return wrapper


@click.group()
@click.option("--debug", is_flag=True)
def cli(debug):
    log = logging.getLogger("")
    log.handlers = []
    log_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    if debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    # Adding a stdout handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(log_format)
    log.addHandler(ch)


@cli.group("analyze")
def analyze_group():
    pass


@analyze_group.command("build")
@click.option(
    "-i",
    "--input-dir",
    help="Directory containing the documents fetched on the website",
    required=True,
    type=str,
)
@click.option(
    "-o", "--output-file", help="json file where processed corpus will be stored"
)
@click.option(
    "-n",
    "--n-jobs",
    help="Number of parallel processes",
    type=int,
    required=False,
    default=-1,
    show_default=True,
)
@time_decorator
def build_command(input_dir: str = None, output_file: str = None, n_jobs: int = None):

    input_dir = os.path.abspath(input_dir)
    output_file = os.path.abspath(output_file)

    if not os.path.isdir(input_dir):
        raise NotADirectoryError("The input directory does not exist")

    if os.path.isfile(output_file):
        click.confirm(
            "The output file already exists. Do you want to overwrite?",
            abort=True,
        )
        click.echo("Overwriting output file: {}".format(os.path.basename(output_file)))

    if n_jobs == -1:
        n_jobs = multiprocessing.cpu_count() - 1

    process_directory(input_dir=input_dir, output_file=output_file, n_jobs=n_jobs)


@cli.group("download")
def download_group():
    """Download resource from vie-publique.fr"""
    pass


@download_group.command("links")
@click.option(
    "-o",
    "--output-file",
    help="text files where links will be written",
    type=str,
    required=True,
)
@click.option(
    "-n",
    "--n-jobs",
    help="Number of parallel processes",
    type=int,
    required=False,
    default=-1,
    show_default=True,
)
@click.option(
    "--start-year",
    help="First year to include in the scrapping",
    type=int,
    required=True,
)
@click.option(
    "--end-year",
    help="End year to include in the scrapping",
    type=int,
    required=True,
)
def links_command(
    output_file: str = None,
    n_jobs: int = None,
    start_year: int = None,
    end_year: int = None,
):
    """Gather links to all documents available on the website"""

    output_file = os.path.abspath(output_file)

    if os.path.isfile(output_file):
        click.confirm(
            "The output file already exists. Do you want to overwrite?",
            abort=True,
        )
        click.echo("Overwriting output file: {}".format(output_file))
        os.remove(output_file)

    if end_year < start_year:
        raise Exception("End year cannot be before start year")

    if n_jobs == -1:
        n_jobs = multiprocessing.cpu_count()

    start_time = datetime.now()
    logger.info(
        "Link extraction started on {}".format(start_time.strftime("%Y/%m/%d %H:%M:%S"))
    )

    gather_link_collection(
        output_file=output_file, n_jobs=n_jobs, start_year=start_year, end_year=end_year
    )

    end_time = datetime.now()

    logger.info(
        "Link extraction ended on {}".format(end_time.strftime("%Y/%m/%d %H:%M:%S"))
    )

    logger.info(
        "Elapsed Time: {}".format(
            timedelta(
                seconds=round(
                    time.mktime(end_time.timetuple())
                    - time.mktime(start_time.timetuple())
                )
            )
        )
    )


@download_group.command("documents")
@click.option(
    "-i",
    "--input-file",
    help="JSON file that contains links to documents",
    type=str,
    required=True,
)
@click.option(
    "-o",
    "--output-dir",
    help="Directory where documents will be stored",
    type=str,
    required=True,
)
@click.option(
    "-n",
    "--n-jobs",
    help="Number of parallel processes",
    type=int,
    required=False,
    default=-1,
    show_default=True,
)
def document_command(
    input_file: str = None, output_dir: str = None, n_jobs: int = None
):
    output_dir = os.path.abspath(output_dir)
    input_file = os.path.abspath(input_file)

    if not os.path.isfile(input_file):
        raise FileNotFoundError("input files does not exist")

    if os.path.isdir(output_dir):
        click.confirm(
            "The output directory already exists. Do you want to resume ?",
            abort=True,
        )
        click.echo("Resuming download: {}".format(output_dir))

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    if n_jobs == -1:
        n_jobs = multiprocessing.cpu_count()

    start_time = datetime.now()
    logger.info(
        "Document download started on {}".format(
            start_time.strftime("%Y/%m/%d %H:%M:%S")
        )
    )

    get_documents(
        link_file=input_file,
        output_dir=output_dir,
        n_jobs=n_jobs,
        timestamp=start_time.strftime("%Y%m%d-%H%M%S"),
    )

    end_time = datetime.now()

    logger.info(
        "Document download ended on {}".format(end_time.strftime("%Y/%m/%d %H:%M:%S"))
    )

    logger.info(
        "Elapsed Time: {}".format(
            timedelta(
                seconds=round(
                    time.mktime(end_time.timetuple())
                    - time.mktime(start_time.timetuple())
                )
            )
        )
    )


if __name__ == "__main__":
    cli()
