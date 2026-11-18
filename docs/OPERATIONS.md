# 运行维护

主服务端口与Compose保持一致。数据保存在records命名卷，应用代码不需要写入权限。

```sh
docker compose logs --tail=80 app
docker compose restart app
docker compose exec -T app pytest -q
docker compose down --remove-orphans
```

健康检查GET /health。失败输入返回原因码，结构性错误422，过大文件413，陈旧复核409。
文件内容最大4MB。批次先计算再原子保存，失败不留半条记录。证据CSV按原始行号定位。
床位看板GET /api/beds.csv导出八张床的当前状态（可收治/清洁中/占用中/待复核/空床）、清洁完成时刻与释放依据；清洁前入住的EARLY段追加在证据CSV。
