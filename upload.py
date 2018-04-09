"""Upload an image url to Imgur album"""
import configparser
import sys

from imgurpython import ImgurClient

CONFIG = configparser.RawConfigParser()
CONFIG.read('praw.ini')


IMGUR_CLIENT_ID = CONFIG['IMGUR']['IMGUR_CLIENT_ID']
IMGUR_CLIENT_SECRET = CONFIG['IMGUR']['IMGUR_CLIENT_SECRET']
IMGUR_ALBUM_ID = CONFIG['IMGUR']['IMGUR_ALBUM_ID']
# to obtain IMGUR_ACCESS_TOKEN and IMGUR_REFRESH_TOKEN
# imgur = ImgurClient(IMGUR_CLIENT_ID, IMGUR_CLIENT_SECRET)
# print(imgur.get_auth_url('pin'))
# credentials = imgur.authorize('PIN_OBTAINED_FROM_URL_ABOVE', 'pin')
# print(credentials)
IMGUR_ACCESS_TOKEN = CONFIG['IMGUR']['IMGUR_ACCESS_TOKEN']
IMGUR_REFRESH_TOKEN = CONFIG['IMGUR']['IMGUR_REFRESH_TOKEN']


def main():
    imgur = ImgurClient(IMGUR_CLIENT_ID, IMGUR_CLIENT_SECRET, IMGUR_ACCESS_TOKEN,
                        IMGUR_REFRESH_TOKEN)

    url = sys.argv[1]
    iconfig = {'album': IMGUR_ALBUM_ID, 'description': url}
    img = imgur.upload_from_url(url, iconfig, False)
    try:
        newurl = img['gifv']
    except KeyError:
        newurl = img['link']
    newurl = newurl.replace('http:', 'https:')
    print('"%s" #%s' % (newurl, url))


if __name__ == "__main__":
    main()
