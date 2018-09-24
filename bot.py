"""Manage Reddit bot"""
from datetime import datetime, timedelta
import json
import logging
from logging.config import dictConfig as logDigConfig
import os
import random
import re
import sys
import unicodedata

import praw
from praw.models import Comment
from prawcore.exceptions import PrawcoreException

from database import BotComment, KeywordCandidate, db, get_images
import export
from utils import (ANIM_EXT, DELETE_BODY_RE, FORCE_TITLE_RE, MAYBE_IMAGE, BoundedSet, GracefulDeath)

with open(os.path.join('templates', 'body.txt'), mode='rt', encoding='utf8') as fbody:
    BODY = fbody.read()
with open(os.path.join('templates', 'force.txt'), mode='rt', encoding='utf8') as fbody:
    BODY_FORCE = fbody.read()
del fbody

ONLY_WORDS = re.compile('[^a-z]')


class RedditBot():
    """Bot to monitor comments and inbox"""

    def __init__(self):
        self._reddit = praw.Reddit()
        self.username = self._reddit.user.me().name
        self.seen_comments = BoundedSet(150)
        self.seen_messages = BoundedSet(150)
        self._next_export = self._calculate_next_export()
        # logging
        self.__init_logger()

    @staticmethod
    def _calculate_next_export():
        """Return next midnight"""
        return datetime.now().replace(hour=0, minute=0) + timedelta(days=1)

    def __init_logger(self):
        try:
            with open(os.path.join("log", "logging.json"), "r", encoding="utf-8") as logconfigf:
                logDigConfig(json.load(logconfigf))
            self._logger = logging.getLogger(self.__class__.__name__)
        except IOError:
            self._logger = logging.getLogger(__name__)
            self._logger.setLevel(logging.DEBUG)
            consoleh = logging.StreamHandler(sys.stdout)
            self._logger.addHandler(consoleh)
            self._logger.debug('No logging.json, reverting to sysout')

    def process_comment(self, comment, template=BODY):
        """Check for matches in a comment and reply"""
        matches = MAYBE_IMAGE.findall(comment.body)
        images = []
        candidate = None
        if matches and BotComment.get_by_parent(comment.id, comment.author.name):
            # already processed
            return None
        for match in matches:
            word = unicodedata.normalize('NFD', match[0]).encode('ascii', 'ignore').decode('utf8')
            word = word.lower()
            word = ONLY_WORDS.sub('', word)
            candiates = get_images(word, match[1] in ANIM_EXT)
            if not candiates:
                candidate = KeywordCandidate.get_or_create(word)
                if candidate.ignored:
                    continue
                candidate.hits = candidate.hits + 1
                self._logger.info('Canditate found "%s" on comment %s', candidate.keyword,
                                  comment.permalink)
                continue
            imageurl = random.choice(candiates)
            images.append('[%s.%s](%s)' % (word, match[1], imageurl))
        if images:
            body = template.format(
                images='\n\n'.join(images), username=self.username, comment_id=comment.id)
            reply = comment.reply(body)
            self._logger.info('Posted comment: %s -> %s', comment.permalink, reply.id)
            db.add(BotComment(reply))
        if images or candidate:
            db.commit()
        return images

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
            self._logger.info('Deleted %s -> %s', comment_id, comment.id)
        db.commit()

    def process_force(self, message):
        """Force a reply to a comment"""
        # find the bot sub, the one the bot mods
        mainsubreddit = next(self._reddit.user.moderator_subreddits())
        if message.author not in list(mainsubreddit.moderator()):
            self._logger.info('Not from mod: %s', message.id)
            return False
        match = FORCE_TITLE_RE.fullmatch(message.subject)
        if not match:
            self._logger.info('No comment id: %s', message.id)
            return False
        comment = self._reddit.comment(match.group(1))
        if not comment or comment.archived or not comment.author:
            self._logger.info('Comment not valid: %s', message.subject)
            return False
        comment.body = message.body
        self._logger.info('Force PM %s', message.fullname)
        images = self.process_comment(comment, BODY_FORCE)
        if images:
            message.reply('%s\n\n%s' % (comment.permalink, '\n\n'.join(images)))
        else:
            self._logger.info('No image found: %s', comment.body)
        return bool(images)

    def process_inbox(self, message):
        """Process different inbox messages: delete"""
        if not message.author:
            return
        if isinstance(message, Comment):
            return
        message.mark_read()
        if message.subject == 'delete':
            self.process_delete(message.body, message.author.name)
        elif message.subject.lower().startswith('force '):
            self.process_force(message)
        else:
            self._logger.info('Ignored message: %s', message.id)

    def _stream_inbox(self, inbox_stream, sighandler):
        """Process all inbox message and returns"""
        for message in inbox_stream:
            if sighandler.received_kill:
                break
            if not message:
                self._logger.debug('One full loop done')
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
            except Exception as expt:  # pylint: disable=W0703
                self._logger.exception(expt)
                continue
        if sighandler.received_kill:
            self._logger.info('Ctrl+c found, extiting')

    def export_to_profile(self):
        """Export the database every midnight"""
        if datetime.now() < self._next_export:
            return
        self._next_export = self._calculate_next_export()
        me = self._reddit.user.me()  # pylint: disable=C0103
        subreddit = self._reddit.subreddit(me.subreddit['display_name'])
        export_md = export.export_md(add_hidden=False)
        existing_posts = list(subreddit.hot())
        previous_post = None
        if existing_posts and existing_posts[0] and existing_posts[0].stickied:
            previous_post = existing_posts[0]
        with open(os.path.join('templates', 'export.txt'), mode='rt', encoding='utf8') as fexport:
            body = fexport.read()
        body = body.format(username=me.name, tabella=export_md, ora=datetime.now().isoformat())
        if previous_post and not previous_post.archived:
            previous_post.edit(body)
            self._logger.info('Export: updated %s', previous_post.permalink)
        elif previous_post and previous_post.archived:
            previous_post.mod.sticky(state=False)
            body = body + '\n\n [Istruzioni precedenti](' + previous_post.permalink + ')'
            self._logger.info('Export: archived %s', previous_post.permalink)
        if not previous_post or previous_post.archived:
            submission = subreddit.submit('Istruzioni', selftext=body)
            submission.mod.sticky(state=True)
            self._logger.info('Export: new post %s', previous_post.permalink)
        self.export_to_subreddit()

    def export_to_subreddit(self):
        """Export the subreddit"""
        subreddit = next(self._reddit.user.moderator_subreddits())
        body = export.export_md(add_hidden=True)
        existing_posts = list(subreddit.hot())
        previous_post = None
        if existing_posts and existing_posts[0] and existing_posts[0].stickied:
            previous_post = existing_posts[0]
        if previous_post and not previous_post.archived:
            previous_post.edit(body)
        elif previous_post and previous_post.archived:
            previous_post.mod.sticky(state=False)
        if not previous_post or previous_post.archived:
            submission = subreddit.submit('Export full', selftext=body)
            submission.mod.sticky(state=True)
            self._logger.info('Export full: new post %s', previous_post.permalink)


def main():
    """Perform bot actions"""
    bot = RedditBot()
    bot.stream_all()


if __name__ == "__main__":
    main()
