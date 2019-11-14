import requests
import time
import json
from email.header import Header
from email.mime.text import MIMEText
import smtplib
import hashlib
import sched
import os
import configparser

from sqllite_util import ConnectSqlite


class SmzdmSpider():

    def __init__(self):
        # 用os模块来读取
        cur_path = os.path.dirname(os.path.realpath(__file__))
        conf_path = os.path.join(cur_path, "config.ini")  # 读取到本机的配置文件
        db_path = os.path.join(cur_path, "data.db")

        self.con = ConnectSqlite(db_path)
        self.create_table()

        self.readConfig(conf_path)

    def create_table(self):
        sql = '''CREATE TABLE IF NOT EXISTS `smzdm_record`(
                  `title` varchar(1000) DEFAULT NULL,
                  `content` varchar(1000) DEFAULT NULL,
                  `price` varchar(1000) DEFAULT NULL,
                  `link` varchar(1000) DEFAULT NULL,
                  `page_url` varchar(1000) DEFAULT NULL,
                  `pic_url` varchar(1000) DEFAULT NULL,
                  `md5` varchar(255) NOT NULL,
                  PRIMARY KEY (`md5`)
                )'''
        result = self.con.create_tabel(sql)
        print('建表成功',str(result))

    # 读取配置文件
    def readConfig(self,path):

        # 调用读取配置模块中的类
        conf = configparser.ConfigParser()
        conf.read(path, encoding="utf-8-sig")

        # smtp_server
        self.smtp_server_host = conf.get("smtp_server", "smtp_server_host")
        self.smtp_server_port = int(conf.get("smtp_server", "smtp_server_port"))
        self.mail_username = conf.get("smtp_server", "smtp_server_username")
        self.mail_password = conf.get("smtp_server", "smtp_server_password")
        self.smtp_server_ssl = int(conf.get("smtp_server", "smtp_server_ssl"))

        # email_receiver
        self.target_mail_address = conf.get("email_receiver", "email_receiver")

        # watch_keys
        self.watch_keys = conf.get("watch_keys", "watch_keys").split(sep=',')

        # interval_sec
        self.interval_sec = int(conf.get("interval", "interval_sec"))

    # 从网络获取数据
    def get_smzdm_data(self):
        c_time = int(time.time())
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, sdch',
            'Host': 'www.smzdm.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36'
        }

        url = 'https://www.smzdm.com/homepage/json_more?timesort=' + str(c_time) + '&p=1'
        r = requests.get(url=url, headers=headers)

        # data = r.text.encode('utf-8').decode('unicode_escape')
        data = r.text

        json_data = json.loads(data)
        core_data = json_data['data']

        resultList = []

        for item in core_data:
            if item.__contains__('type'):
                if item['type'] == 'ad':
                    continue
            title = item['article_title']
            content = item['article_content_all']
            price = ''
            if 'article_price' in item.keys():
                price = item['article_price']
            link = ''
            if 'article_link' in item.keys():
                link = item['article_link']
            page_url = item['article_url']
            pic_url = ''
            if 'article_pic' in item.keys():
                pic_url = item['article_pic']
            result = {
                'title': title,
                'content': content,
                'price': price,
                'link': link,
                'page_url': page_url,
                'pic_url': pic_url
            }
            resultList.append(result)
        return resultList

    # 发送邮件
    def send_mail(self, data, key, title):
        username = self.mail_username
        password = self.mail_password
        to_addr = self.target_mail_address.split(',')
        msg = MIMEText(data,"html", 'utf-8')
        msg['From'] = 'SMZDM最新优惠'
        msg['To'] = 'Target'
        msg['Subject'] = Header(title, 'utf-8').encode()
        server = None;
        # 判断是否ssl
        if self.smtp_server_ssl==1:
            server = smtplib.SMTP_SSL(self.smtp_server_host, self.smtp_server_port)
        else:
            server = smtplib.SMTP(self.smtp_server_host, self.smtp_server_port)
            server.set_debuglevel(1)
            # server.starttls()
        server.login(username, password)
        server.sendmail(username, to_addr, msg.as_string())
        server.quit()

    # md5
    @staticmethod
    def md5(str):
        print(str)
        m = hashlib.md5()
        m.update(str.encode(encoding='utf-8'))
        return m.hexdigest()

    # 此数据是否已经在数据库中存在过
    def is_data_exist(self, result):
        # tempResult = sorted(result.items(), key=lambda result: result[0])
        # 根据page_url的md5,判断是否在数据库中
        sql = 'SELECT * FROM smzdm_record where md5 = "%s"' % self.md5(result['page_url'])
        print(sql)
        cursor = self.con.execute_sql(sql)
        if len(cursor.fetchall()) > 0:
            return True
        else:
            return False

    # 插入数据
    def insert_data(self, result):
        # tempResult = sorted(result.items(), key=lambda result: result[0])
        sql = """INSERT INTO smzdm_record(title,content,price,link,page_url,pic_url,md5) VALUES (?, ?, ?, ?, ?, ?, ?)"""
        value = [(result['title'], result['content'], result['price'], result['link'], result['page_url'], result['pic_url'], self.md5(result['page_url']))]
        print(self.md5(result['page_url']))
        self.con.insert_table_many(sql, value)

    # 启动一次查询全过程
    def search(self):
        print('启动搜索')
        resultList = self.get_smzdm_data()
        for result in resultList:
            for key in self.watch_keys:
                if result['title'].find(key) != -1:
                    if not self.is_data_exist(result):
                        print('发现新商品', str(result))
                        htmldata = "<div>{title}</div><div style='margin-top:10px'>{content}</div><div style='margin-top:10px'>{price}</div><div style='margin-top:10px'><a href='{url}'>{url}</a></div><div style='margin-top:10px'><img src='{pic_url}'/></div>".format(title=result['title'],content = result['content'],price=result['price'],url=result['page_url'],pic_url=result['pic_url'])
                        self.send_mail(htmldata, key, result['title'])
                        self.insert_data(result)


# 定时执行器
class ScheduleManager:
    def __init__(self, callback, interval_sec):
        self.schedule = sched.scheduler(time.time, time.sleep)
        self.callback = callback
        self.interval_sec = interval_sec

    def func(self):
        self.callback()
        self.schedule.enter(self.interval_sec, 0, self.func, ())

    def start(self):
        self.schedule.enter(0, 0, self.func, ())
        self.schedule.run()


if __name__ == '__main__':
    spider = SmzdmSpider()
    manager = ScheduleManager(spider.search, spider.interval_sec)
    manager.start()
