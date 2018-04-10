"""Export database"""
from sqlalchemy import distinct

from database import Keyword, Image, db


def export_md(add_hidden=False):
    """Export database to markdown"""
    imagesets = [key[0] for key in db.query(distinct(Image.imageset)).all()]
    data = {}
    for imageset in imagesets:
        dbkeys = db.query(Keyword).filter_by(imageset=imageset)
        if not add_hidden:
            dbkeys = dbkeys.filter_by(hidden=False)
        keywords = [keyword.keyword for keyword in dbkeys.all()]
        data[imageset] = {
            'urls': [image.image for image in db.query(Image).filter_by(imageset=imageset).all()],
            'keywords': keywords
        }
    with open('export.md', mode='wt', encoding='utf8') as ofile:
        ofile.write('|Parola|Immagini|\n')
        ofile.write('|:-|:-|\n')
        for item in data.values():
            if not item['keywords']:
                continue
            ofile.write('|%s|' % ', '.join(item['keywords']))
            images = ['[%d](%s)' % ((idx + 1), url) for idx, url in enumerate(item['urls'])]
            ofile.write(' '.join(images))
            ofile.write('|\n')


if __name__ == "__main__":
    export_md()
