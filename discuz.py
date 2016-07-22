# -*- coding: utf-8 -*-

import requests
import re
import time

from requests.exceptions import ReadTimeout
# 论坛网址,这里只需要论坛地址和header
import config
import sched
import logging
from bs4 import BeautifulSoup

'''
 config.home_url 为php结尾的论坛首页,最后不带/
 config.headers http 请求header
 config.reply_form+url = home_url + mod=post&action=reply&fid={:d}&tid={:d}&extra=page%3D1&" \
                 "replysubmit=yes&infloat=yes&handlekey=fastpost&inajax=1
 自带了格式化,方便一些.
'''


def today():
    time_str = time.strftime("%m.%d", time.localtime())
    return time_str


def gmt_time():
    """

    :rtype: object
    """
    gmt_time = 'GMT:' + time.strftime('%m-%d %H:%M:%S', time.gmtime(time.time()))
    return gmt_time


class Discuz(object):
    def __init__(self):
        self.user_pattern = re.compile(r'uid:(\w+)')
        self.password_pattern = re.compile(r'password:(.+)')
        self.comment_id_pattern = re.compile(r'pid=(\d+)')
        self.page_number_pattern = re.compile(r'共 (\d+) 页')
        self.html_content = ''
        self.form_hash = ''
        self.req = requests.session()
        self.operate = ""
        self.temp_soup = ''
        self.uid = 0  # 用户uid
        self.tid_pattern = re.compile(r'thread-(\d+)-1-1.html')
        # re 匹配模式
        self.hash_pattern = re.compile(r'<input type="hidden" name="formhash" value="(.+?)" />')

    def login(self):
        with open('user.txt', encoding='utf8') as f:
            user = f.read()
        username = re.search(self.user_pattern, user).group(1)
        password = re.search(self.password_pattern, user).group(1)
        self.login_name(username=username, password=password)

    def login_name(self, username=0, password=0):
        self.uid = username
        print(username, password)
        postdate = dict(username=username, password=password)
        self.operate = self._get_response(config.form_url + '/member.php?mod=logging&action=login&loginsubmit'
                                                            '=yes&infloat=yes&inajax=1', postdate)
        if re.search('现在将转入登录前页面', self.operate.text):
            print('登录成功')
            self.get_form_hash(config.home_url)
        else:
            print('出错啦')
            print(self.operate.text)
            exit()

    def _get_response(self, url, data=None):
        # 此处还有bug,只能进行一次处理,第二次出错,还是会退出脚本
        try:
            if data is not None:
                req = self.req.post(url, data=data, headers=config.headers)
            else:
                req = self.req.get(url, headers=config.headers)
            return req
        except requests.exceptions.RequestException as error:
            logging.exception(error)
            print('error时间:' + gmt_time())
            schedule = sched.scheduler(time.time, time.sleep)
            schedule.enter(delay=300, priority=0, action=self._get_response, argument=(self, url, data))
            return self._get_response(self, url, data)
        except requests.exceptions.ConnectionError as connect_error:
            logging.exception(connect_error)
            print('conect_error时间:' + gmt_time())
            schedule = sched.scheduler(time.time, time.sleep)
            schedule.enter(delay=300, priority=0, action=self._get_response, argument=(self, url, data))
            return self._get_response(self, url, data)
        finally:
            pass

    def get_form_hash(self, url):
        # 找到隐藏hash的位置,使用re的research功能查找,比用BS4方便一些
        soup = self.req.get(url)
        self.form_hash = self.hash_pattern.search(soup.text).group(1)
        # self.form_hash = re.search(r'<input type="hidden" name="formhash" value="(.+?)" />', soup.text).group(1)
        print(self.form_hash)

    # fid版块号码+tid帖子,拼凑url.后续可以尝试从帖子页面抓取生成回复地址
    def reply_fid_tid(self, fid, tid, message):
        reply_url = config.form_url + '/forum.php?mod=post&action=reply&fid={:d}&tid={:d}&extra=page%3D1&replysubmit' \
                                      '=yes&infloat=yes&handlekey=fastpost&inajax=1'.format(fid, tid)
        assert isinstance(reply_url, object)
        # 先打印一遍回帖内容,好知道如果失败是哪一贴
        print(message)
        post_time = time.time()
        # 长度必须大于10,且要加进行encode成gbk编码
        if len(message) < 20:
            message += '\n'
            message += str(today())
            message += "          "
        reply = dict(message=message.encode("gbk"), posttime=int(post_time), formhash=self.form_hash, usesig=1,
                     subject='', connect_publish_t=0)
        html = self._get_response(reply_url, data=reply)
        soup = BeautifulSoup(html.content, "html.parser")
        result = re.search('succee', soup.text)
        if result:
            print('回帖成功')
        else:
            print(soup.contents)
        print('------------------')

    # 点评,已验证
    def comment_tid_pid(self, tid, pid, page, message):
        comment_url = config.form_url + '/forum.php?mod=post&action=reply&comment=yes&tid={:d}&pid={:d}&extra=page%3D' \
                                        '{:d}&replysubmit=yes&infloat=yes&inajax=1'.format(tid, pid, page)
        if len(message) < 10:
            message += "          "
        reply = dict(formhash=self.form_hash, handlekey='comment', message=message.encode("gbk"), commentsubmit='true')
        html = self._get_response(comment_url, data=reply)
        soup = BeautifulSoup(html.content, "html.parser")
        result = re.search('succee', soup.text)
        if result:
            print('点评成功')
        else:
            print(soup.contents)
        print('------------------')

    # 发帖,已验证,关键字参数,带默认一些值,方便自定义。
    def publish_fid_subject(self, fid, subject, msg, allownoticeauthor=1, readperm=0, credits=0, reply_times=1,
                            membertimes=1, random=10):
        publish_url = config.form_url + '/forum.php?mod=post&action=newthread&fid=' + str(
            fid) + '&extra=&topicsubmit=yes'
        post_data = {'formhash': self.form_hash,
                     'message': msg.encode('gbk'),
                     'subject': subject.encode('gbk'),
                     'posttime': int(time.time()),
                     'addfeed': '1',
                     'allownoticeauthor': str(allownoticeauthor),  # 通知作者
                     'checkbox': '0',
                     'newalbum': '',
                     'readperm': str(readperm),  # 阅读权限
                     'rewardfloor': '',
                     'rushreplyfrom': '',
                     'rushreplyto': '',
                     'save': '',
                     'stopfloor': '',
                     'uploadalbum': '',
                     'usesig': '1',
                     'replycredit_extcredits': str(credits),  # 单次中奖金额(一次中奖的金额),此处填0,则无中奖金额
                     'replycredit_times': str(reply_times),  # 奖励次数
                     'replycredit_membertimes': str(membertimes),  # 每人最多中奖次数
                     'replycredit_random': str(random),  # 中奖几率
                     'wysiwyg': '0'}
        html = self._get_response(publish_url, data=post_data)
        soup = BeautifulSoup(html.content, "html.parser")
        print(soup)
        tie = soup.find(href=re.compile(config.form_url + '/thread-\d+-1-1.html'))
        tid = re.search('thread-(\d+)-1-1.html', tie['href']).group(1)
        print(tid)
        return int(tid)  # 返回数字,保证可以发帖

    # 找出共多少页
    def find_page_number(self, url):
        html = self.req.get(url)
        soup = BeautifulSoup(html.content, "html.parser")
        page_soup = soup.find('span', title=self.page_number_pattern)
        page_number = re.search('\d+', page_soup.get_text()).group()
        print('共' + page_number + '页')
        return page_number
