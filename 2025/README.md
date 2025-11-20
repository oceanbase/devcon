2025年产品发布会,基于pyseekdb做的一个嵌入式/remote模式的混搜demo应用.

使用 init_data.py 初始化数据,使用query_tool.py 做查询.
torism中包含了初始化数据,一个文件一条数据,一个文件中包含:山名(一行),地名(一行),高度(一行),介绍(其余)
如果下载sentence-transformers模型比较慢，可以设置环境变量来下载.
HF_ENDPOINT=https://hf-mirror.com
