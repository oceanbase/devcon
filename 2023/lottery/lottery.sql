DROP DATABASE IF EXISTS lottery;
CREATE DATABASE lottery;
USE lottery;

# 奖品
# NOTE：art_name 可以存放ascii-art格式数据，可以以图片的形式展示奖品
CREATE TABLE prize (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `level` bigint unsigned NOT NULL COMMENT '奖品级别，展示时排序使用',
  `type` varchar(60) NOT NULL COMMENT '奖品类别',
  `name` varchar(200) NOT NULL COMMENT '奖品名称',
  `count` bigint NOT NULL COMMENT '奖品个数',
  `art_name` LONGTEXT NOT NULL COMMENT '奖品ascii-art展示',
  PRIMARY KEY (`id`)
);
CREATE UNIQUE INDEX prize_index_name ON prize(`name`);

# 抽奖候选人
CREATE TABLE `candidate` (
  `id` varchar(60) NOT NULL,
  `name` varchar(60) NOT NULL COMMENT '姓名',
  `prize_id` bigint unsigned COMMENT '获奖',
  PRIMARY KEY (`id`)
);

# 导入数据前调整一些参数
# global 参数调整后需要重新连接客户端才会生效
SET GLOBAL secure_file_priv = "";
set global ob_query_timeout=36000000000;

# 导入奖品数据
# 由于奖品的"图片"比较大，直接放文件中导入
source prizes/keyboard.sql;
source prizes/airpods.sql;
source prizes/charger.sql;

# 查看抽奖人数
SELECT COUNT(1) from candidate;

# 查看候选人列表
SELECT name, id from candidate;

# 展示三等奖奖品
SELECT name from prize where type='三等奖' \G;
select art_name from prize where type='三等奖' \G;

# 红色展示
# echo -n -e '\e[31m' ; echo select name from lottery.prize | obclient -N -h127.0.0.1 -P55800 -uroot -Doceanbase -A ; echo -n -e '\e[0m'

# 导入抽奖候选人
load data infile '/tmp/candidate.txt' ignore into table candidate(name, id);
load data infile '/tmp/candidate.txt' ignore into table candidate fields terminated by '\t' (name, id);

