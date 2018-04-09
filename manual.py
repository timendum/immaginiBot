"""Force a reply to a comment"""
from sys import argv

from praw import Reddit

from bot import RedditBot


def force(comment_id, image):
    """Main function"""
    reddit = Reddit()
    comment = reddit.comment(comment_id)
    comment.body = image
    bot = RedditBot()
    print(bot.process_comment(comment))


def main():
    """Force a comment"""
    force(argv[1], argv[2])


if __name__ == "__main__":
    main()
