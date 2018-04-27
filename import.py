"""This module allow to import data in database"""
import sys

import sqlalchemy
import toml

from database import Image, Keyword, KeywordCandidate, db


def import_source():
    """Parse `images.toml` and update databases"""
    with open('images.toml', 'rt', encoding='utf8') as infile:
        newdefinitions = toml.load(infile)
    # images section
    for keyw, images in newdefinitions['images'].items():
        if isinstance(images, list):
            for image in images:
                db.merge(Image(image, keyw))
        else:
            db.merge(Image(images, keyw))
        db.merge(Keyword(keyw, keyw))
    # alias section
    for keyw, kalias in newdefinitions['alias'].items():
        db.merge(Keyword(keyw, kalias))
    # hidden section
    for keyw, hidden in newdefinitions['hidden'].items():
        db.query(Keyword).get(keyw).hidden = hidden
    # ignored
    for keyw, ignored in newdefinitions['ignored'].items():
        KeywordCandidate.get_or_create(keyw).ignored = ignored
    db.commit()


def delete_imported():
    """Delete imported candidates, KeywordCandidate where Keyword exists with the same keyword"""
    candidates = db.query(KeywordCandidate,
                          Keyword).filter(Keyword.keyword == KeywordCandidate.keyword)
    for candidate, _ in candidates:
        db.delete(candidate)
    db.commit()


def truncate_images():
    """Remove all keywords"""
    try:
        db.query(Image).delete()
        db.query(Keyword).delete()
        db.commit()
    except sqlalchemy.exc.SQLAlchemyError as sqlexc:
        db.rollback()
        print(sqlexc)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'd':
        print('Deleting')
        truncate_images()
    import_source()
    delete_imported()
    print('Imported')
