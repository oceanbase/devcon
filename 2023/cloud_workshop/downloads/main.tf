variable "sql_user_password" {
  type      = string
  nullable  = false
  sensitive = true
  description = "SQL用户密码，要求至少两个数字，两个小写字母，两个大写字母以及两个特殊字符。"
}

## 暂时使用临时OB自建的镜像中心，后续开源会发布到官方库
terraform {
  required_providers {
    oceanbase = {
      source  = "registry.oceanbase.com/oceanbase/oceanbase"
      version = "~> 0.0.6"
    }
  }
  required_version = ">= 1.0.0"
}

resource "oceanbase_cluster" "example" {
  cluster_type    = "SHARED"
  node_size       = "1C4G"
  region          = "ap-southeast-1"
  available_zones = ["a"]
}

output "cluster_output" {
  value = oceanbase_cluster.example
}

resource "oceanbase_sql_user" "example"{
  cluster_id = oceanbase_cluster.example.id
  ## SQL User名字可以自定义
  user_name ="admin"
  password = var.sql_user_password
}

resource "oceanbase_ip_allow_list" "example"{
   cluster_id = oceanbase_cluster.example.id
   ## 临时对所有公网访问公开，真实使用建议修改当前公网出口IP/IP段
   security_ips =["0.0.0.0/0"]
}

data "oceanbase_connection_string" "example"{
   cluster_id = oceanbase_cluster.example.id
   user_name=oceanbase_sql_user.example.user_name
}

output  "connection_string"  {
   value=data.oceanbase_connection_string.example
}
