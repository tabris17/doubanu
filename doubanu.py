# -*-coding: utf-8 -*-
"""
doubanu.py
"""

import threading
import sys
import sqlite3
import argparse
import logging
import re
import os
import tempfile
import requests
import time


URL_BASE = 'https://www.douban.com/'
URL_LOGIN = 'https://www.douban.com/accounts/login'
URL_MINE = 'https://www.douban.com/mine/'
URL_MY_CONTACTS = 'https://www.douban.com/contacts/list?start={offset}'
URL_USER = 'https://www.douban.com/people/{user_id}/'
URL_USER_CONTACTS = 'https://www.douban.com/people/{user_id}/contacts'

REL_UNKNOWN = 0     # 未知
REL_SELF = 1        # 自指
REL_BLOCK_ME = 2    # 拉黑我的
REL_BLOCKED = 3     # 被我拉黑
REL_FOLLOWING = 4   # 被我关注
REL_UNRELATED = 5   # 无关联
REL_DISABLE = 6     # 已注销
REL_ABNORMAL = 7    # 帐号异常


def main(args):
    """
    Main function
    """
    arg_parser = argparse.ArgumentParser(description='Find the guys who blocked you.')
    arg_parser.add_argument('schedule', help='specify a sqlite database file for saving schedule')
    arg_group = arg_parser.add_argument_group('authentication')
    arg_group.add_argument('-u', '--username', help='set username to your douban account')
    arg_group.add_argument('-p', '--password', help='set password to your douban account')
    arg_parser.add_argument('-d', '--debug', action='store_true', default=False, help='print debug information')
    parsed_args = arg_parser.parse_args(args[1:])

    schedule = parsed_args.schedule
    username = parsed_args.username
    password = parsed_args.password

    logging.basicConfig(level=logging.DEBUG if parsed_args.debug else logging.INFO)

    def open_db():
        """
        Open and initialize database
        """
        logging.info('open schedule file "%s"', schedule)
        conn = sqlite3.connect(schedule)
        logging.debug('create table if not exists')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS `session` (
                `user_id`	TEXT NOT NULL,
                `cookie`	TEXT NOT NULL,
                `created`	TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                `last_access`	TEXT,
                PRIMARY KEY(`user_id`)
            );
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS `schedule` (
                `id`	INTEGER PRIMARY KEY AUTOINCREMENT,
                `user_id`	TEXT NOT NULL UNIQUE,
                `nickname`  TEXT NOT NULL,
                `created`	TIMESTAMP DEFAULT (datetime(CURRENT_TIMESTAMP, 'localtime')),
                `relation`	INTEGER NOT NULL DEFAULT 0,
                `user_info` TEXT,
                `done`	INTEGER DEFAULT 0
            );
        ''')
        return conn

    def login():
        """
        Login
        """
        logging.info('login...')
        cursor = db_conn.cursor()
        cursor.execute('SELECT `cookie`, `user_id` FROM `session` LIMIT 1;')
        result = cursor.fetchone()
        cursor.close()

        if result is None:
            logging.debug('session does not exists')
            if username is None or password is None:
                print('need username and password')
                sys.exit()
            response = requests.get(URL_BASE)
            cookie_bid = response.cookies['bid']
            logging.debug('received cookie, bid=%s', cookie_bid)

            form_data = {
                'source': 'index_nav',
                'form_email': username,
                'form_password': password,
                'remember': 'on',
            }
            response_text = response.text

            if 'name="captcha-id"' in response_text:
                logging.info('download captcha image...')
                pattern_captcha_id = re.compile(
                    r'<input type="hidden" name="captcha-id" value="(.+)"/>'
                )
                pattern_captcha_image = re.compile(
                    r'<img id="captcha_image" src="(.+)" alt="captcha" '
                    r'class="captcha_image" title="'
                )
                form_data['captcha-id'] = pattern_captcha_id.search(response_text).groups()[0]
                captcha_image_url = pattern_captcha_image.search(response_text).groups()[0]
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as captcha_image:
                    captcha_image.write(requests.get(captcha_image_url).content)
                os.system(captcha_image.name)
                form_data['captcha-solution'] = input('captcha:')

            response = requests.post(URL_LOGIN, data=form_data, headers={
                'Referer': URL_BASE,
                'Upgrade-Insecure-Requests': '1',
                'Origin': 'https://www.douban.com',
                'Content-Type': 'application/x-www-form-urlencoded',
            }, cookies={
                'bid': cookie_bid
            }, allow_redirects=False)
            cookie_dbcl2 = response.cookies.get('dbcl2')
            if cookie_dbcl2 is None:
                print('the captcha code is not accepted')
                sys.exit()
            logging.debug('received cookie, dbcl2=%s', cookie_dbcl2)
            cookie = 'bid={bid}; dbcl2={dbcl2}'.format(bid=cookie_bid, dbcl2=cookie_dbcl2)
            response = requests.get(URL_MINE, headers={
                'Cookie': cookie
            }, allow_redirects=False)
            user_id = re.search(r'/people/(.+)/$', response.headers['Location']).groups()[0]
            logging.debug('my user id is "%s"', user_id)
            db_conn.execute('INSERT INTO `session` (`cookie`, `user_id`) VALUES (?, ?);', (cookie, user_id))
        else:
            logging.debug('session exists and checking validity...')
            cookie, user_id = result
            response = requests.get(URL_MINE, headers={
                'Cookie': cookie
            }, allow_redirects=False)
            if response.headers['Location'].startswith(URL_LOGIN):
                logging.info('session invalid, try to login again...')
                db_conn.execute('DELETE FROM `session`')
                db_conn.commit()
                return login()
            db_conn.execute('''
                UPDATE `session` 
                SET `last_access` = datetime(CURRENT_TIMESTAMP, 'localtime');
            ''')

        db_conn.commit()
        return cookie, user_id

    def get_url(url, retry_times=3):
        """
        Get url content
        """
        try:
            time.sleep(1)
            logging.info('open url %s', url)
            response = requests.get(url, headers={'Cookie': cookie})
            if response.status_code == requests.codes.ok:
                return response.text
            raise requests.exceptions.HTTPError()
        except requests.exceptions.RequestException as error:
            if retry_times == 0:
                raise error
            return get_url(url, retry_times - 1)

    def get_my_contacts():
        """
        Get my contacts
        """
        max_page = 100
        page_size = 20
        pattern_my_contacts_user = re.compile(r'<a href="https:\/\/www.douban.com\/people\/(.+)\/" title="(?:.+)">(.+)<\/a>')

        cursor = db_conn.cursor()
        cursor.execute('SELECT * FROM `schedule` WHERE `user_id` = ?;', (my_user_id, ))
        result = cursor.fetchone()
        cursor.close()
        if result is not None:
            return

        logging.info('fetching my contacts user list...')
        for page in range(0, max_page):
            content = get_url(URL_MY_CONTACTS.format(offset=page * page_size))
            rows = [(result.group(1), result.group(2)) for result in pattern_my_contacts_user.finditer(content)]
            if len(rows) == 0:
                break
            db_conn.execute('INSERT OR IGNORE INTO `schedule` (`user_id`, `nickname`, `relation`, `done`) VALUES (?, ?, ?, ?);', (my_user_id, '', REL_SELF, 1))
            db_conn.executemany('INSERT OR IGNORE INTO `schedule` (`user_id`, `nickname`, `relation`) VALUES (?, ?, ?);', [row + (REL_FOLLOWING, ) for row in rows])
            db_conn.commit()
        logging.info('done')

    def get_user_info(user_id, relation):
        """
        Get user info
        """
        if relation == REL_UNKNOWN:
            SIGN_UNRELATED = 'class="a-btn-add mr10 add_contact"'
            SIGN_FOLLOWING = u'<span class="user-cs">已关注</span>'
            SIGN_BLOCKED = 'id="ban-cancel"'
            SIGN_BLOCK_ME = u'已经将你列入了黑名单'

            user_url = URL_USER.format(user_id=user_id)
            try:
                content = get_url(user_url)

                if SIGN_UNRELATED in content:
                    relation = REL_UNRELATED
                elif SIGN_BLOCK_ME in content:
                    logging.info('%s(%s) block me', user_id, user_url)
                    relation = REL_BLOCK_ME
                elif SIGN_FOLLOWING in content:
                    relation = REL_FOLLOWING
                elif SIGN_BLOCKED in content:
                    relation = REL_BLOCKED
                elif user_url not in content:
                    relation = REL_DISABLE
            except requests.exceptions.HTTPError:
                relation = REL_ABNORMAL

        if relation not in (REL_DISABLE, REL_ABNORMAL):
            content = get_url(URL_USER_CONTACTS.format(user_id=user_id))
            rows = [(result.group(1), result.group(2)) for result in get_user_info.PATTERN_USER.finditer(content)]
            db_conn.executemany('INSERT OR IGNORE INTO `schedule` (`user_id`, `nickname`) VALUES (?, ?);', rows)

        db_conn.execute('UPDATE `schedule` SET `relation` = ?, `done` = 1 WHERE `user_id` = ?;', (relation, user_id))
        db_conn.commit()

    get_user_info.PATTERN_USER = re.compile(r'<dd><a href="https:\/\/www.douban.com\/people\/(.+)\/">(.+)<\/a><\/dd>')

    with open_db() as db_conn:
        cookie, my_user_id = login()
        get_my_contacts()

        while True:
            cursor = db_conn.cursor()
            cursor.execute('SELECT `user_id`, `relation` FROM `schedule` WHERE `done` = 0 LIMIT 1;')
            result = cursor.fetchone()
            cursor.close()
            if result is None:
                break
            get_user_info(*result)

    logging.info('all done.')

if __name__ == '__main__':
    main(sys.argv)
