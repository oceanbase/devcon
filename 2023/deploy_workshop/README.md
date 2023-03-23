# 快速体验 OceanBase

我们已经在体验环境的家目录（/home/oceanbase）下准备好了本次体验需要的安装部。

## 安装 all-in-one
```bash
tar -xzf oceanbase-all-in-one-4.1.0.0-100120230323143519.el7.x86_64.tar.gz
cd oceanbase-all-in-one/bin/
./install.sh
source ~/.oceanbase-all-in-one/bin/env.sh
```

## 部署DEMO OceanBase 数据库 并 创建租户
```bash
obd demo
obd cluster tenant create demo
```

## 安装 OB-Sysbench 并执行测试
```bash
sudo yum install -y ob-sysbench-1.0.20-11.el7.x86_64.rpm	
obd test sysbench demo
```

## 销毁 Demo 集群
```bash
obd cluster destroy demo
```


# 使用 Docker 体验 OceanBase

## 启动 OceanBase 容器
```bash
sudo docker run --name obstandalone -p 2881:2881 -d oceanbase/oceanbase-ce 
```

## 查看启动进度
```bash
sudo docker logs obstandalone -f
```

## 连接到 OceanBase 数据库
```bash
# 使用obclient连接
obclient -uroot@sys -h127.1 -P2881 
# 使用镜像自带连接脚本
sudo docker exec -it obstandalone ob-mysql sys
```

## 销毁 OceanBase 容器
```bash
sudo docker rm -f obstandalone
```

# 在 K8s 上部署 OceanBase 数据库

## 部署 ob-operator
```bash
cd /home/oceanbase/ob-operator/deploy
kubectl apply -f crd.yaml 
kubectl apply -f operator.yaml
```

## 监听当前POD
本条命令应在新的窗口中执行，用于监听当前POD的情况，可以不执行。
```bash
watch kubectl get pods -A 
```

## 部署 OceanBase 数据库
```bash
kubectl get node -A
kubectl label node <nodename> <ob.zone=zonename>
kubectl create namespace obcluster
kubectl apply -f obcluster.yaml
```

## 创建租户
```bash
kubectl apply -f tenant.yaml
```

## 连接到 OceanBase 数据库
```bash
kubectl get svc -n ocluster
obclient -h<ip> -uroot@sys -P2881 -A -c -Doceanbase
```

## 部署生态监控组件
```bash
kubectl apply -f prometheus/
kubectl apply -f grafana/
```

## 进行 Sysbench 测试
```bash
kubectl apply -f sysbench/prepare.yaml
kubectl apply -f sysbench/run.yaml
```
