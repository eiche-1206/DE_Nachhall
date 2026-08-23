# scripts/

日常操作的脚本。都能从仓库任何位置调用，内部会自己 `cd` 到根目录。

| 脚本 | 做什么 |
|---|---|
| `init.sh` | **首次必跑**。建表 + 写入种子数据。幂等 |
| `up.sh [服务…]` | 起服务。不带参数起全部 |
| `down.sh [--rm]` | 停。默认只停不删；`--rm` 连容器一起删。两种都不动 `./data` |
| `logs.sh [服务]` | 跟日志。默认跟 `worker` |
| `import.sh <链接>` | 命令行导入一期素材，等价于界面右上角的 ＋ |
| `disk.sh` | 看素材占了多少地方，按期列出 |
| `fix-perms.sh` | 把 `data/` 属主改回当前用户（服务以 root 跑，写出来的文件归 root） |
| `check.sh` | 全量检查：后端 ruff + mypy + pytest，前端 tsc + eslint |
| `gen-api-types.sh` | 改了后端接口之后重新生成前端类型 |

## 典型的一天

```bash
./scripts/up.sh                     # 起来
./scripts/import.sh https://www.logo.de/logo-vom-...-100.html
./scripts/logs.sh                   # 盯着处理完
# 打开 http://localhost:8000 开练
./scripts/down.sh                   # 收工
```

## 和 tools/ 的区别

`tools/` 放的是**一次性的验证工具**——Sprint 0 用来实测浏览器 seek 精度的
基准页、支持 Range 的临时静态服务器。它们完成使命之后留在那儿作为证据，
不是日常会用到的东西。

`scripts/` 放的是**反复要用的**。
