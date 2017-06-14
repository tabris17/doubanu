# doubanu
豆瓣爬虫，找出拉黑你的人

## 环境需求
- python3（只在python3.4下跑过，其他版本未测试）
- requests

## 使用方法
python doubanu.py -u 你的用户名 -p 你的密码 保存进度的数据库文件路径

Sample：

python doubanu.py -u yourname@douban.com -p 123456 douban.db

## 获取结果

当程序发现拉黑你的用户时会打印在console里，同时也会将结果写入数据库的schedule表内。

可以使用sqlite数据库访问软件来进行检索，比如 DB Browser for SQLite http://sqlitebrowser.org/ 

查询语句：

`select * from schedule where relation=2;`
