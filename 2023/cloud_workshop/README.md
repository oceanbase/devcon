# 云服务会议使用资源说明

- downloads/world.sql

这是样例 DB，开发者可以导入到 OB 免费集群（MySQL模式）的实例中做使用体验。

- downloads/main.tf

这是 OB 云服务提供的 Terraform 插件(Terraform-provider-oceanbase)的样例文件。使用该样例文件可以快速创建出集群实例。
[Terraform 安装](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)，设置环境变量（windows terminal 使用 set）如下：

```
 export OCEANBASE_PRIVATE_KEY=?
 export OCEANBASE_PUBLIC_KEY=?
```
