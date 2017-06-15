# doubanu
豆瓣爬虫，找出拉黑你的人

## 环境需求
- python3（只在python3.4下跑过，其他版本未测试）
- requests

## 使用方法

`python doubanu.py -u <用户名> -p <密码> -o <结果文件路径> <进度文件路径>`

或者在命令行下运行：

`doubanu.exe -u <用户名> -p <密码> -o <结果文件路径> <进度文件路径>`

Sample：

`python doubanu.py -u yourname@douban.com -p 123456 -o who_block_me.log douban.db`

`doubanu.exe -u yourname@douban.com -p 123456 -o who_block_me.log douban.db`

## 获取结果

当程序发现拉黑你的用户时会打印在console里，同时也会将结果写入数据库的schedule表内。

可以使用sqlite数据库访问软件来进行检索，比如 DB Browser for SQLite http://sqlitebrowser.org/ 

查询语句：

`select * from schedule where relation=2;`

新增`-o/--output`参数。可以将结果保存到日志文件中。
