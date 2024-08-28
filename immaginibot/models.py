import os
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import toml
from thefuzz import process as processfuzz

from .utils import ANIM_RE

if TYPE_CHECKING:
    from praw.reddit import Comment


@dataclass(frozen=True)
class Image:
    url: str
    reddit_id: str | None
    animated: bool


@dataclass(frozen=True)
class ImageSet:
    id: str
    keywords: frozenset[str]
    images: frozenset[Image]
    hidden_keywords: frozenset[str]
    hide: bool = False


IMAGE_SETS: set[ImageSet] = set()


def get_fuzzy_word(word: str) -> str | None:
    keywords = [i for s in IMAGE_SETS for i in s.keywords]
    keyword, score = processfuzz.extractOne(word, keywords)  # type: ignore
    if score > 93:
        return keyword
    return None


def get_images(word: str, animated=None) -> list[Image] | None:
    """Get all images for `word`, if possibile match also `animated`"""
    all_images_sets = [s for s in IMAGE_SETS for i in s.keywords if i == word]
    if not all_images_sets:
        return None
    if animated is not None:
        a_images_set = [i for s in all_images_sets for i in s.images if i.animated == animated]
        if a_images_set:
            return a_images_set
    return [i for s in all_images_sets for i in s.images]


def _toml_get_words(key: str, item, plural: str, singular: str) -> list[str]:
    rvalue = item.get(plural, None)
    if rvalue:
        if isinstance(rvalue, list):
            return [r.lower() for r in rvalue]
        else:
            raise TypeError(f"{key}.{plural} not handled")
    else:
        rvalue = item.get(singular, None)
        if rvalue:
            if isinstance(rvalue, str):
                return [rvalue.lower()]
            else:
                raise TypeError(f"{key}.{singular} not handled")
    return []


def _toml_make_image(item) -> Image:
    reddit_id = None
    if isinstance(item, list):
        url = item[0]
        reddit_id = item[1]
    elif isinstance(item, str):
        url = item
    else:
        raise TypeError(f"Image not handled {item}")
    animated = ANIM_RE.search(url) is not None
    return Image(url, reddit_id, animated)


def load_images_from_toml() -> None:
    with open(os.path.join("config", "images.toml")) as infile:
        newdefinitions = toml.load(infile)
    for key, value in newdefinitions.items():
        # keywords
        keywords = frozenset([key.lower()] + _toml_get_words(key, value, "aliases", "alias"))
        # hidden_keywords
        hidden_keywords = frozenset(_toml_get_words(key, value, "hiddens", "hidden"))
        # hide
        hide = bool(value.get("hide", False))
        # image
        rvalue = value.get("image", None)
        if rvalue:
            images = frozenset([_toml_make_image(rvalue)])
        else:
            rvalue = value.get("images", None)
            if rvalue:
                images = frozenset([_toml_make_image(i) for i in rvalue])
            else:
                raise TypeError("No images!")
        # DONE!
        IMAGE_SETS.add(ImageSet(key, keywords, images, hidden_keywords, hide))


load_images_from_toml()


@dataclass
class BotComment:
    id: str
    parent_id: str
    parent_author: str
    deleted = False
    richtext = False

    @staticmethod
    def get_by_parent(parent_id: str) -> "BotComment | None":
        """Find all active comments by parent_id and parent_author"""
        if parent_id not in BOTCOMMENTS:
            return None
        e = BOTCOMMENTS[parent_id]
        if e.deleted:
            return None
        return e

    @staticmethod
    def save(e: "BotComment | None" = None) -> None:
        if e:
            BOTCOMMENTS[e.parent_id] = e
        save_status_to_toml()

    @classmethod
    def from_reddit(cls, comment: "Comment") -> "BotComment":
        parent = comment.parent()
        return BotComment(
            comment.id, parent.id, parent.author.name if parent.author else "[deleted]"
        )


BOTCOMMENTS: dict[str, BotComment] = {}


def load_status_from_toml() -> None:
    try:
        with open(os.path.join("config", "status.toml")) as infile:
            tcomments = toml.load(infile)
        for c in tcomments["comments"]:
            e = BotComment(**c)
            BOTCOMMENTS[e.parent_id] = e
    except FileNotFoundError:
        return


def save_status_to_toml() -> None:
    tstatus = {"comments_old": []}
    try:
        with open(os.path.join("config", "status.toml")) as infile:
            tstatus.update(toml.load(infile))
    except FileNotFoundError:
        return
    tstatus["comments"] = sorted(
        [asdict(c) for c in BOTCOMMENTS.values()], key=lambda a: a["id"], reverse=True
    )
    tstatus["comments_old"] = tstatus["comments"][100:] + tstatus["comments_old"]
    tstatus["comments"] = tstatus["comments"][0:100]
    with open(os.path.join("config", "status.toml"), "w") as outfile:
        toml.dump(tstatus, outfile)


load_status_from_toml()

if __name__ == "__main__":
    from pprint import pprint

    pprint(IMAGE_SETS)
    pprint(BOTCOMMENTS.values())
