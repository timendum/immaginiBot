"""Manage Reddit bot"""
import json
import logging
from logging.config import dictConfig as logDigConfig
import random
import sys

import praw
from praw.models import Comment

from database import BotComment, KeywordCandidate, db, get_images
from utils import ANIM_EXT, MAYBE_IMAGE, BoundedSet, GracefulDeath, DELETE_BODY_RE, FORCE_TITLE_RE

with open('body.txt', mode='rt', encoding='utf8') as fbody:
    BODY = fbody.read()


class RedditBot():
    """Bot to monitor comments and inbox"""

    def __init__(self):
        self._reddit = praw.Reddit()
        self.username = self._reddit.user.me().name
        self.seen_comments = BoundedSet(150)
        self.seen_messages = BoundedSet(150)
        # logging
        self.__init_logger()

    def __init_logger(self):
        try:
            with open("logging.json", "r", encoding="utf-8") as logconfigf:
                logDigConfig(json.load(logconfigf))
            self._logger = logging.getLogger(self.__class__.__name__)
        except IOError:
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(logging.DEBUG)
            consoleh = logging.StreamHandler(sys.stdout)
            consoleh.terminator = ''
            self._logger.addHandler(consoleh)
            self._logger.debug('No logging.json, reverting to sysout')


    def process_comment(self, comment):
        """Check for matches in a comment and reply"""
        matches = MAYBE_IMAGE.findall(comment.body)
        images = []
        candidate = None
        for match in matches:
            candiates = get_images(match[0], match[1] in ANIM_EXT)
            if not candiates:
                candidate = KeywordCandidate.get_or_create(match[0])
                candidate.hits = candidate.hits + 1
                continue
            imageurl = random.choice(candiates)
            images.append('[%s.%s](%s)' % (match[0], match[1], imageurl))
        if images:
            body = BODY.format(
                images='\n\n'.join(images), username=self.username, comment_id=comment.id)
            reply = comment.reply(body)
            self._logger.info('\nCommento %s -> %s', comment.id, reply.id)
            db.add(BotComment(reply))
        if images or candidate:
            db.commit()
        return images, candidate

    def process_delete(self, body, author):
        """If body and author match, delete child comments"""
        match = DELETE_BODY_RE.fullmatch(body)
        if not match:
            return
        comment_id = match.group(1)
        comments = BotComment.get_by_parent(comment_id, author)
        for comment in comments:
            self._reddit.comment(comment.id).delete()
            comment.deleted = True
            self._logger.info('\nDeleted %s -> %s', comment_id, comment.id)
        db.commit()

    def process_force(self, message):
        """Force a reply to a comment"""
        # find the bot sub, the one the bot mods
        mainsubreddit = next(self._reddit.user.moderator_subreddits())
        if message.author not in list(mainsubreddit.moderator()):
            # only from other mods
            return False
        match = FORCE_TITLE_RE.fullmatch(message.subject)
        if not match:
            return False
        comment = self._reddit.comment(match.group(1))
        comment.body = message.body
        self._logger.info('\nForce %s', message.fullname)
        images, _ = self.process_comment(comment)
        if images:
            message.reply('%s\n\n%s' % (comment.permalink, str(images)))

    def process_inbox(self, message):
        """Process different inbox messages: delete"""
        if not message.author:
            return
        if isinstance(message, Comment):
            return
        if message.subject == 'delete':
            message.mark_read()
            self.process_delete(message.body, message.author.name)
        if message.subject.startswith('force '):
            self.process_force(message)
        else:
            self._logger.info('\nIgnored message: %s', message.id)

    def stream_all(self):
        """Monitor comments and inbox"""
        sighandler = GracefulDeath()
        while True:
            try:
                if sighandler.received_kill:
                    break
                subreddit = self._reddit.user.me().multireddits()[0]
                comment_stream = subreddit.stream.comments(pause_after=2)
                inbox_stream = self._reddit.inbox.stream(pause_after=0)
                for comment in comment_stream:
                    if sighandler.received_kill:
                        break
                    if comment:
                        if comment.id in self.seen_comments:
                            continue
                        self._logger.debug('.')
                        self.seen_comments.add(comment.id)
                        self.process_comment(comment)
                    else:
                        # process inbox
                        while True:
                            message = next(inbox_stream)
                            if not message:
                                break
                            if message.id in self.seen_messages:
                                continue
                            break
                        if message:
                            self._logger.debug(',')
                            self.seen_messages.add(message.id)
                            self.process_inbox(message)
            except Exception as expt:  # pylint: disable=W0703
                self._logger.exception(expt)
                continue
        if sighandler.received_kill:
            self._logger.info('\nCtrl+c found, extiting')


def main():
    """Perform bot actions"""
    bot = RedditBot()
    bot.stream_all()


if __name__ == "__main__":
    main()
