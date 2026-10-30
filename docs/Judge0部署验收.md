# Judge0部署与验收

当前本机未检测到Docker命令，也未配置Judge0服务；本文为后续执行手册，不是部署完成证明。项目现有docker-compose.yml不包含Judge0，不能用它启动判题服务。

## 部署准备

在专门的隔离主机/VM上选择维护中的固定发行版，核对其安全公告、内核/cgroup要求、API/worker/PostgreSQL/Redis拓扑和镜像摘要后部署。本文不把旧版协议文档所对应的镜像当作已通过安全审查的部署推荐。记录实际镜像摘要、配置摘要、主机资源与网络规则；管理端口仅允许面试后端/运维访问，不挂载宿主敏感目录。

本轮客户端协议按[Judge0官方API文档](https://ce.judge0.com/)核对：异步提交token后轮询，认证凭据放请求头，先查询语言列表再确定Python language_id。配置字段参考[官方配置源码](https://github.com/judge0/judge0/blob/v1.13.1/judge0.conf)，部署时仍须以所选版本为准。

必须核实`ENABLE_NETWORK=false`和`ALLOW_ENABLE_NETWORK=false`，以及worker/队列与CPU/墙钟/内存/进程/文件大小限制。客户端请求禁网并不代替服务端禁止用户改开关，也不证明宿主网络隔离有效。探针只认可config_info明确返回两个网络开关false；缺字段视为未核实，拒绝执行。

## 配置与探测

在backend/.env填写JUDGE0_URL、可选JUDGE0_API_KEY和已核实的Python JUDGE0_LANGUAGE_ID，不把凭据放URL。根目录执行：

```powershell
.\backend\.venv\Scripts\python.exe evals/sandbox_probe.py --output sandbox-config.json
.\backend\.venv\Scripts\python.exe evals/sandbox_probe.py --execute --output sandbox-execution.json
```

默认仅请求config_info和指定language信息。--execute显式提交4个合成程序，期待AC=3、WA=4、TLE=5、编译错误=6。退出2表示无服务配置；退出1表示错误或条件未通过；退出0仍需看execution_verified，因为只读通过不代表执行过。输出不含地址、密钥、代码或实际stdout，isolation_verified始终false。

## 真实隔离验收（仍待执行）

- 在受控测试网络布置canary，验证默认无法外联、客户端不可开启网络；保留canary记录、网络策略与运行结果。连接一个不存在的地址失败不能证明禁网。
- 在远端执行可控CPU/睡眠、内存、进程和超输出程序，确认限制真正生效；验证文件/目录权限与无宿主敏感挂载。不要在宿主Python运行这些程序。
- 并发/排队测试记录worker数、服务端队列峰值、拒绝率、超时与资源曲线。应用层2个作业不代表远端只运行2个程序；客户端超时可能留下已提交任务。
- 对正确/错误/TLE/编译/非文本输出核对状态，比较客观结果与应用0.6主观+0.4客观合分；供应商故障不能记考生零分。
- 对401/429/5xx、断网、慢响应、进程重启验证保留轮次、恢复与计费；当前未实现远端token持久化和跨重启提交去重，应记录可能重复执行的成本。

完成后将原始JSON、镜像/配置摘要、网络与容量证据登记到开发日志，才可更新真实部署/隔离状态。
