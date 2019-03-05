"""ORM utilities"""
import datetime
from typing import Any  # pylint: disable=W0611

from fuzzywuzzy import process as processfuzz
from sqlalchemy import (create_engine, Column, String, Boolean, Index, Integer)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from utils import ANIM_RE

engine = create_engine("sqlite:///db/images.sqlite3")  # pylint: disable=C0103

Base = declarative_base()  # type: Any # pylint: disable=C0103
Session = sessionmaker(bind=engine)  # pylint: disable=C0103
db = Session()  # pylint: disable=C0103


class Keyword(Base):  # pylint: disable=R0903
    """ORM bean for the Keyword"""
    __tablename__ = "keywords"

    keyword = Column(String(100), primary_key=True)
    imageset = Column(String(100))
    hidden = Column(Boolean)

    __table_args__ = (Index("ix_keywords_imageset", "imageset"), )

    def __init__(self, keyword, imageset, hidden=0):
        self.keyword = keyword
        self.imageset = imageset
        self.hidden = hidden


class KeywordCandidate(Base):  # pylint: disable=R0903
    """ORM bean for new keywords candidate"""
    __tablename__ = "candidates"

    keyword = Column(String(100), primary_key=True)
    hits = Column(Integer)
    last_hit = Column(Integer)
    ignored = Column(Boolean)

    def __init__(self, keyword):
        self.keyword = keyword
        self.hits = 0
        self.last_hit = int(datetime.datetime.now().timestamp())
        self.ignored = False

    @classmethod
    def get_or_create(cls, keyword):
        """Get an Entity or create (and persist) it"""
        entry = db.query(cls).get(keyword)
        if not entry:
            entry = KeywordCandidate(keyword)
            db.add(entry)
        else:
            entry.last_hit = int(datetime.datetime.now().timestamp())
        return entry


class Image(Base):  # pylint: disable=R0903
    """ORM bean for the Keyword"""
    __tablename__ = "imagesets"

    image = Column(String(100), primary_key=True)
    imageset = Column(String(100))
    animated = Column(Boolean)

    def __init__(self, image, imageset):
        self.image = image
        self.imageset = imageset
        self.animated = ANIM_RE.search(image) is not None

    def __str__(self):
        return self.image

    def __repr__(self):
        return '%s(%s)' % (self.image, self.imageset)


def get_images(word: str, animated=None):
    """Get all images for `word`, if possibile match also `animated`"""
    keyword = db.query(Keyword).get(word)
    if not keyword:
        return None
    images = db.query(Image).filter_by(imageset=keyword.imageset)
    if animated is not None:
        aimages = images.filter(Image.animated == animated)
        if aimages.count():
            images = aimages
        else:
            images = images.filter(Image.animated != animated)
    return images.all()

def get_fuzzy_images(word: str):
    keywords = [k.keyword for k in db.query(Keyword).all()]
    keyword, score = processfuzz.extractOne(word, keywords)
    if score > 93:
        return keyword
    return None

class BotComment(Base):  # pylint: disable=R0903
    """ORM bean for the Keyword"""
    __tablename__ = "comments"
    __table_args__ = (Index("ix_comments_parent", "parent_id"), )

    id = Column(String(10), primary_key=True)  # pylint: disable=C0103
    body = Column(String(100))
    parent_id = Column(String(10))
    parent_author = Column(String(20))
    deleted = Column(Boolean)

    def __init__(self, comment):
        self.id = comment.id  # pylint: disable=C0103
        self.body = comment.body
        parent = comment.parent()
        self.parent_id = parent.id
        self.parent_author = parent.author.name if parent.author else '[deleted]'
        self.deleted = False

    @classmethod
    def get_by_parent(cls, parent_id):
        """Find all active comments by parent_id and parent_author"""
        query = db.query(cls)
        query = query.filter_by(parent_id=parent_id)
        query = query.filter_by(deleted=False)
        return query.first()


if __name__ == "__main__":
    Base.metadata.create_all(engine)
