"""This module allow to import data in database"""
from database import Keyword, Image, db, KeywordCandidate

import toml


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
    db.commit()


def delete_imported():
    """Delete imported candidates, KeywordCandidate where Keyword exists with the same keyword"""
    candidates = db.query(KeywordCandidate,
                          Keyword).filter(Keyword.keyword == KeywordCandidate.keyword)
    for candidate, _ in candidates:
        db.delete(candidate)
    db.commit()


if __name__ == "__main__":
    import_source()
    delete_imported()
