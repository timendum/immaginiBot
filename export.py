"""Export database"""
from io import StringIO
from collections import OrderedDict

from sqlalchemy import distinct

from database import Image, Keyword, db


def _export(add_hidden=False):
    """Export database to markdown"""
    imagesets = [key[0] for key in db.query(distinct(Image.imageset)).all()]
    imagesets = sorted(imagesets)
    data = OrderedDict()
    for imageset in imagesets:
        dbkeys = db.query(Keyword).filter_by(imageset=imageset).filter(Keyword.keyword != imageset)
        if not add_hidden:
            dbkeys = dbkeys.filter_by(hidden=False)
        dbkeys = dbkeys.order_by(Keyword.keyword)
        keywords = [imageset] + [keyword.keyword for keyword in dbkeys.all()]
        data[imageset] = {
            'urls': [image.image for image in db.query(Image).filter_by(imageset=imageset).all()],
            'keywords': keywords
        }
    with StringIO() as ofile:
        ofile.write('|Parola|Immagini|\n')
        ofile.write('|:-|:-|\n')
        for item in data.values():
            if not item['keywords']:
                continue
            ofile.write('|%s|' % ', '.join(item['keywords']))
            images = ['[%d](%s)' % ((idx + 1), url) for idx, url in enumerate(item['urls'])]
            ofile.write(' '.join(images))
            ofile.write('|\n')
        return ofile.getvalue()


def export_md(add_hidden=False):
    with open('export.md', mode='wt', encoding='utf8') as ofile:
        ofile.write(_export(add_hidden))


if __name__ == "__main__":
    export_md()
