"""Manage Reddit bot"""

import copy
import json
import logging
import os
import random
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from logging.config import dictConfig as logDigConfig
from typing import NamedTuple, cast

import praw
from prawcore.exceptions import PrawcoreException

from . import export
from .models import BotComment, Image, get_fuzzy_word, get_images
from .utils import (
    ANIM_EXT,
    DELETE_BODY_RE,
    FORCE_TITLE_RE,
    MAYBE_IMAGE,
    STATIC_EXT,
    BoundedSet,
    GracefulDeath,
)

ONLY_WORDS = re.compile("[^a-z_]")


class ImageMatch(NamedTuple):
    word: str
    ext: str
    image: Image
    fuzzy: bool


class ImmaginiBot:
    """Bot to monitor comments and inbox"""

    def __init__(self):
        # logging
        self.__init_logger()
        # Reddit stuff
        self._reddit = praw.Reddit()
        self.username = self._reddit.user.me().name
        self._logger.debug("Reddit login ok")
        self.seen_comments = BoundedSet(150)
        self.seen_messages = BoundedSet(150)
        self._next_export = self._calculate_next_export()
        self._mainsubreddit = self._reddit.user.me().moderated()[0]
        self._creator = self._mainsubreddit.moderator()[0]  # type: praw.reddit.Redditor
        self._mods = list(self._mainsubreddit.moderator())  # type: list[praw.reddit.Redditor]
        # texts
        self.templates = {
            "body_txt": "",
            "force_txt": "",
            "body_json": {},
            "force_json": {},
        }
        with open(os.path.join("config", "body.txt"), encoding="utf8") as fbody:
            self.templates["body_txt"] = fbody.read()
        with open(os.path.join("config", "force.txt"), encoding="utf8") as fbody:
            self.templates["force_txt"] = fbody.read()
        with open(os.path.join("config", "body.json"), encoding="utf8") as fbody:
            self.templates["body_json"] = json.load(fbody)
        with open(os.path.join("config", "force.json"), encoding="utf8") as fbody:
            self.templates["force_json"] = json.load(fbody)
        del fbody

    @staticmethod
    def _calculate_next_export():
        """Return next midnight"""
        return datetime.now().replace(hour=0, minute=0) + timedelta(days=1)

    def __init_logger(self):
        try:
            with open(os.path.join("config", "logging.json")) as logconfigf:
                logDigConfig(json.load(logconfigf))
            self._logger = logging.getLogger(self.__class__.__name__)
        except OSError:
            self._logger = logging.getLogger(__name__)
            self._logger.setLevel(logging.DEBUG)
            consoleh = logging.StreamHandler(sys.stdout)
            self._logger.addHandler(consoleh)
            self._logger.debug("No logging.json, reverting to sysout")

    def find_matches(self, comment: praw.reddit.Comment) -> list[ImageMatch]:
        matches = MAYBE_IMAGE.findall(comment.body)
        images: list[ImageMatch] = []
        for match in matches:
            fuzzy = False
            word = unicodedata.normalize("NFD", match[0]).encode("ascii", "ignore").decode("utf8")
            word = word.lower()
            word = ONLY_WORDS.sub("", word)
            candiates = get_images(word, match[1].lower() in ANIM_EXT)
            if not candiates:
                fuzzy_word = get_fuzzy_word(word)
                if fuzzy_word:
                    fuzzy = True
                    self._logger.info("Fuzzy %s -> %s", word, fuzzy_word)
                    candiates = get_images(fuzzy_word, match[1].lower() in ANIM_EXT)
                    word = fuzzy_word
            if not candiates:
                self._logger.info(
                    'Canditate found "%s" on comment %s',
                    word,
                    comment.permalink,
                )
                continue
            else:
                image = random.choice(candiates)
                images.append(ImageMatch(word, match[1], image, fuzzy))
        return images

    def process_comment(self, comment: praw.reddit.Comment, force=False) -> None | BotComment:
        """Check for matches in a comment and reply"""
        if BotComment.get_by_parent(comment.id):
            # already processed
            return None
        images = self.find_matches(comment)
        if not images:
            return None
        return self.make_comment(comment, images, force)

    def make_comment(
        self, comment: praw.reddit.Comment, images: list[ImageMatch], force=False
    ) -> BotComment:
        txts_img = []
        for i in images:
            ext = i.ext
            if i.ext not in (ANIM_EXT if i.image.animated else STATIC_EXT):
                ext = random.choice(ANIM_EXT if i.image.animated else STATIC_EXT)
            txts_img.append(f"[{i.word}.{ext}]({i.image.url})")
        force = force or any([i.fuzzy for i in images])
        body = self.templates["body_txt" if not force else "force_txt"].format(
            images="\n\n".join(txts_img),
            username=self.username,
            comment_id=comment.id,
        )
        reply = cast("praw.reddit.Comment", comment.reply(body))
        self._logger.info("Posted comment: %s -> %s", comment.permalink, reply.id)
        bcomment = BotComment.from_reddit(reply)
        edited = False
        try:
            edited = self.to_richtext(images, bcomment, force)
        except Exception as e:
            self._logger.error(e)
        if edited:
            bcomment.richtext = True
        BotComment.save(bcomment)
        return bcomment

    def to_richtext(self, images: list[ImageMatch], reply: BotComment, force=False) -> bool:
        if len(images) != 1:
            return False
        i = images[0]
        if not i.image.reddit_id:
            return False
        ext = i.ext
        if i.ext not in (ANIM_EXT if i.image.animated else STATIC_EXT):
            ext = random.choice(ANIM_EXT if i.image.animated else STATIC_EXT)
        rtjson = copy.deepcopy(self.templates["body_json"])
        rtjson["document"][0]["c"][0]["t"] = f"{i.word}.{ext}"
        rtjson["document"][0]["c"][0]["u"] = i.image.url
        rtjson["document"][0]["c"][0]["f"][0][2] = len(rtjson["document"][0]["c"][0]["t"])
        rtjson["document"][1]["id"] = i.image.reddit_id
        for e in rtjson["document"][2]["c"]:
            if "u" in e:
                e["u"] = e["u"].format(
                    username=self.username,
                    comment_id=reply.id,
                )
        if force:
            rtjson["document"] = [self.templates["force_json"]] + rtjson["document"]
        z = self._reddit.post(
            "/api/editusertext",
            data={
                "api_type": "json",
                "thing_id": f"t1_{reply.id}",
                "richtext_json": json.dumps(rtjson),
            },
        )
        self._logger.debug(json.dumps(rtjson))
        self._logger.debug(z)
        return True

    def process_delete(self, body: str, author: str) -> None:
        """If body and author match, delete child comments"""
        match = DELETE_BODY_RE.fullmatch(body)
        if not match:
            return
        comment_id = match.group(1)
        comment = BotComment.get_by_parent(comment_id)
        if not comment:
            return
        if author != comment.parent_author and author not in self._mods:
            return
        self._reddit.comment(id=comment.id).delete()
        comment.deleted = True
        self._logger.info("Deleted %s -> %s", comment_id, comment.id)
        BotComment.save()

    def process_force(self, message) -> bool:
        """Force a reply to a comment"""
        # find the bot sub, the one the bot mods
        if message.author not in self._mods:
            self._logger.info("Not from mod: %s", message.id)
            return False
        match = FORCE_TITLE_RE.fullmatch(message.subject)
        if not match:
            self._logger.info("No comment id: %s", message.id)
            return False
        comment = self._reddit.comment(id=match.group(1))
        if not comment or comment.archived or not comment.author:
            self._logger.info("Comment not valid: %s", message.subject)
            return False
        comment.body = message.body
        self._logger.info("Force PM %s", message.fullname)
        botcomment = self.process_comment(comment, True)
        if botcomment:
            message.reply(f"Fatto [commento]({comment.permalink})")
        else:
            self._logger.info("No image found: %s", comment.body)
        return bool(botcomment)

    def process_inbox(self, message):
        """Process different inbox messages: fw or delete"""
        if not message.author:
            return
        if isinstance(message, praw.reddit.Comment):
            if message.subject in ("comment reply"):
                return
            self._logger.info("Username mention: %s", message.context)
            message.mark_read()
            self._creator.message(
                subject="FW from " + message.author.name + ": " + message.subject,
                message="\n\n".join([message.context, message.body]),
            )
            return
        message.mark_read()
        if message.subject == "delete":
            self.process_delete(message.body, message.author.name)
        elif message.subject.lower().startswith("force "):
            self.process_force(message)
        else:
            # Forward to creator
            self._creator.message(
                f"FW from {message.author.name}: {message.subject}",
                message=message.body,
            )

    def _stream_inbox(self, inbox_stream, sighandler):
        """Process all inbox message and returns"""
        for message in inbox_stream:
            if sighandler.received_kill:
                break
            if not message:
                self._logger.debug("One full loop done")
                return
            if message.id in self.seen_messages:
                continue
            self.seen_messages.add(message.id)
            self.process_inbox(message)

    def _stream_comments(self, comment_stream, inbox_stream, sighandler):
        """Process all comments and all inbox messages"""
        for comment in comment_stream:
            if sighandler.received_kill:
                break
            if comment:
                if comment.id in self.seen_comments:
                    continue
                self.seen_comments.add(comment.id)
                self.process_comment(comment)
            else:
                self._stream_inbox(inbox_stream, sighandler)
                self.export_to_profile()

    def stream_all(self):
        """Monitor comments and inbox"""
        sighandler = GracefulDeath()
        self._logger.debug("Starting first loop")
        while True:
            try:
                if sighandler.received_kill:
                    break
                subreddit = self._reddit.user.me().multireddits()[0]
                comment_stream = subreddit.stream.comments(pause_after=2)
                inbox_stream = self._reddit.inbox.stream(pause_after=0)
                self._stream_comments(comment_stream, inbox_stream, sighandler)
            except PrawcoreException as prawexcept:
                self._logger.debug(prawexcept)
            except Exception as expt:
                self._logger.exception(expt)
                continue
        if sighandler.received_kill:
            self._logger.info("Ctrl+c found, extiting")

    def export_to_profile(self):
        """Export the database every midnight"""
        title = "Istruzioni"
        if datetime.now() < self._next_export:
            return
        self._next_export = self._calculate_next_export()
        me = self._reddit.user.me()
        subreddit = cast("praw.reddit.Subreddit", self._reddit.subreddit(me.subreddit.display_name))
        export_md = export.export_md(add_hidden=False)
        posts = list(subreddit.hot())
        previous_post: "None | praw.reddit.Submission" = None
        if posts and posts[0] and posts[0].stickied and posts[0].title == title:
            previous_post = posts[0]
        elif len(posts) > 1 and posts[1] and posts[1].stickied and posts[1].title == title:
            previous_post = posts[1]
        with open(os.path.join("config", "export.txt"), encoding="utf8") as fexport:
            body = fexport.read()
        body = body.format(username=me.name, tabella=export_md, ora=datetime.now().isoformat())
        if previous_post and not previous_post.archived:
            previous_post.edit(body)
            self._logger.info("Export: updated %s", previous_post.permalink)
        elif previous_post and previous_post.archived:
            self._reddit.user.pin(previous_post, state=False)
            body = body + "\n\n [Istruzioni precedenti](" + previous_post.permalink + ")"
            self._logger.info("Export: archived %s", previous_post.permalink)
        if not previous_post or previous_post.archived:
            submission = subreddit.submit(title, selftext=body)
            self._reddit.user.pin(submission, state=True)
            submission.mod.lock()
            self._logger.info("Export: new post %s", submission.permalink)
        self.export_to_subreddit()

    def export_to_subreddit(self):
        """Export the subreddit"""
        body = export.export_md(add_hidden=True)
        existing_posts = list(self._mainsubreddit.hot())
        previous_post: "None | praw.reddit.Submission" = None
        if existing_posts and existing_posts[0] and existing_posts[0].stickied:
            previous_post = existing_posts[0]
        if previous_post and not previous_post.archived:
            previous_post.edit(body)
        elif previous_post and previous_post.archived:
            previous_post.mod.sticky(state=False)
        if not previous_post or previous_post.archived:
            submission = self._mainsubreddit.submit("Export full", selftext=body)
            submission.mod.sticky(state=True)
            submission.mod.lock()
            self._logger.info("Export full: new post %s", submission.permalink)


def main():
    """Perform bot actions"""
    bot = ImmaginiBot()
    bot.stream_all()


if __name__ == "__main__":
    main()
