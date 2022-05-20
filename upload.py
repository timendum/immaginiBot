"""Upload an image url to Imgur album"""
import configparser
import sys

CONFIG = configparser.RawConfigParser()
CONFIG.read("praw.ini")


IMGUR_CLIENT_ID = CONFIG["IMGUR"]["IMGUR_CLIENT_ID"]
IMGUR_CLIENT_SECRET = CONFIG["IMGUR"]["IMGUR_CLIENT_SECRET"]
IMGUR_ALBUM_ID = CONFIG["IMGUR"]["IMGUR_ALBUM_ID"]
# to obtain IMGUR_REFRESH_TOKEN
# see https://apidocs.imgur.com/#authorization-and-oauth
IMGUR_REFRESH_TOKEN = CONFIG["IMGUR"]["IMGUR_REFRESH_TOKEN"]


def main():

    response = requests.request(
        "POST",
        "https://api.imgur.com/oauth2/token",
        data={
            "refresh_token": IMGUR_REFRESH_TOKEN,
            "client_id": IMGUR_CLIENT_ID,
            "client_secret": IMGUR_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
    )
    response.raise_for_status()
    access_token = response.json()["access_token"]

    url = sys.argv[1]
    response = requests.request(
        "POST",
        "https://api.imgur.com/3/image",
        headers={"Authorization": "Bearer " + access_token},
        data={"image": url, "album": IMGUR_ALBUM_ID, "description": url},
    )
    response.raise_for_status()
    newimg = response.json()

    try:
        newurl = newimg["data"]["gifv"]
    except KeyError:
        newurl = newimg["data"]["link"]
    newurl = newurl.replace("http:", "https:")
    print('"%s" #%s' % (newurl, url))


if __name__ == "__main__":
    main()
