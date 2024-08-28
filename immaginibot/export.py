"""Export database"""

from collections import OrderedDict
from datetime import date
from io import StringIO

from praw import Reddit

from .models import IMAGE_SETS


def export_md(add_hidden):
    """Export database to markdown"""
    imagesets = sorted(IMAGE_SETS, key=lambda i: i.id)
    data = OrderedDict()
    for imageset in imagesets:
        if imageset.hide:
            continue
        data[imageset] = {
            "urls": [image.url for image in imageset.images],
            "keywords": imageset.keywords,
        }
    with StringIO() as ofile:
        ofile.write("|Parola|Immagini|\n")
        ofile.write("|:-|:-|\n")
        for item in data.values():
            if not item["keywords"]:
                continue
            ofile.write("|%s|" % ", ".join(item["keywords"]))
            images = ["[%d](%s)" % ((idx + 1), url) for idx, url in enumerate(item["urls"])]
            ofile.write(" ".join(images))
            ofile.write("|\n")
        return ofile.getvalue()


def export_md_file(add_hidden=True):
    """Export images database to a markdown file"""
    with open("export.md", mode="w", encoding="utf8") as ofile:
        ofile.write(export_md(add_hidden))


def export_reddit(add_hidden=False):
    """Export images database to Reddit"""
    reddit = Reddit()
    mainsubreddit = next(reddit.user.moderator_subreddits())
    mainsubreddit.submit("Export " + date.today().isoformat(), export_md(add_hidden))


if __name__ == "__main__":
    export_md_file(True)
